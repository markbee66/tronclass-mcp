import json
import shutil
import sqlite3

import pytest

from tronclass.config import ROOT
from tronclass.database import CourseRepository, DataError


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "學生資料 含空白.db"
    shutil.copy2(ROOT / "sample_data" / "course.db", path)
    return path


def test_student_snapshot_keeps_conflicting_sources_and_attachment_locations(database):
    snapshot = CourseRepository(database).snapshot("S11200001")
    assert len(snapshot["courses"]) == 4
    assignment = next(a for a in snapshot["assignments"] if a["assignment_id"] == "C01-HW3")
    correction = next(a for a in snapshot["announcements"] if a["announcement_id"] == "A04")
    assert assignment["due"] == "2026-11-06 23:59"
    assert "12:00" in correction["content"]
    assert {c["locator_type"] for c in snapshot["attachment_chunks"]} == {"page", "slide", "paragraph"}


def test_private_rows_teacher_material_and_hidden_scores_are_not_exported(database):
    with sqlite3.connect(database) as con:
        con.execute("INSERT INTO students VALUES ('OTHER', '其他學生秘密')")
        con.execute("INSERT INTO submissions VALUES ('OTHER','C01-HW3',NULL,'其他學生繳交',99,1,NULL)")
        con.execute("INSERT INTO attendance_records VALUES ('SECRET','OTHER','C01','2026-10-30','其他學生缺席','','','')")
        con.execute("INSERT INTO quiz_attempts VALUES ('OTHER','C01-Q1',1,NULL,'',99,1)")
        con.execute("INSERT INTO materials(course_id,source,section,content,visibility) VALUES ('C01','','','教師秘密答案','teacher_only')")
        con.execute("UPDATE submissions SET score=9876,score_published=0,score_note='隱藏評語'")
        con.execute("UPDATE quiz_attempts SET score=9876,score_published=0 WHERE student_id='S11200001'")
        con.execute("UPDATE student_grade_items SET score=9876,actual_score=9876,score_published=0")
        con.execute("UPDATE student_course_grades SET final_grade=9876,raw_grade=9876,published=0")
    snapshot = CourseRepository(database).snapshot("S11200001")
    text = json.dumps(snapshot, ensure_ascii=False)
    for secret in ("其他學生秘密", "其他學生繳交", "其他學生缺席", "教師秘密答案", "9876", "隱藏評語"):
        assert secret not in text
    for table in ("submissions", "quiz_attempts", "student_grade_items", "student_course_grades", "attendance_records"):
        assert all(row["student_id"] == "S11200001" for row in snapshot[table])


def test_database_is_read_only_and_student_parameter_cannot_change_query(database):
    repository = CourseRepository(database)
    con = repository.connect()
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM courses")
    finally:
        con.close()
    with pytest.raises(DataError, match="沒有此學生"):
        repository.snapshot("' OR 1=1 --")


def test_missing_database_is_not_silently_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(DataError, match="找不到資料庫"):
        CourseRepository(path).snapshot("S11200001")
    assert not path.exists()
