"""Read-only, parameterized access to one student's visible SQLite data.

This module has no Streamlit or model dependencies, so a future MCP server can
reuse it. It deliberately preserves conflicting records for System 1 testing.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path


class DataError(RuntimeError):
    pass


class CourseRepository:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def connect(self):
        if not self.path.is_file():
            raise DataError(f"找不到資料庫：{self.path}。請確認 TRONCLASS_DB_PATH。")
        try:
            con = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only = ON")
            return con
        except sqlite3.Error as exc:
            raise DataError(f"無法開啟 SQLite 資料庫：{exc}") from exc

    def snapshot(self, student_id: str) -> dict:
        """Return a deterministic, consistent snapshot; never include hidden grades.

        Enrollment comes from student_course_grades in this mock schema. There is
        intentionally no arbitrary SQL endpoint and no teacher-only export.
        """
        try:
            with closing(self.connect()) as con:
                con.execute("BEGIN")
                student = con.execute(
                    "SELECT student_id, name FROM students WHERE student_id = ?", (student_id,)
                ).fetchone()
                if student is None:
                    raise DataError("資料庫中沒有此學生，請確認 TRONCLASS_STUDENT_ID。")

                def rows(sql, params=()):
                    return [dict(row) for row in con.execute(sql, params)]

                enrolled = "course_id IN (SELECT course_id FROM student_course_grades WHERE student_id = ?)"
                result = {
                    "student": dict(student),
                    "semester": rows("SELECT * FROM semester ORDER BY key"),
                    "no_class_days": rows("SELECT * FROM no_class_days ORDER BY date"),
                }
                shared = {
                    "courses": "SELECT * FROM courses",
                    "course_instructors": "SELECT * FROM course_instructors",
                    "course_outline": "SELECT * FROM course_outline",
                    "announcements": "SELECT * FROM announcements",
                    "assignments": "SELECT * FROM assignments",
                    "learning_materials": "SELECT * FROM learning_materials",
                    "quizzes": "SELECT * FROM quizzes",
                    "grade_categories": "SELECT * FROM grade_categories",
                    "discussions": "SELECT * FROM discussions",
                }
                for name, sql in shared.items():
                    result[name] = rows(f"{sql} WHERE {enrolled} ORDER BY rowid", (student_id,))
                result["materials"] = rows(
                    f"SELECT chunk_id, course_id, source, section, content FROM materials "
                    f"WHERE visibility = 'student' AND {enrolled} ORDER BY chunk_id", (student_id,)
                )
                result["attachments"] = rows(
                    f"SELECT f.*, lm.course_id FROM attachments f "
                    f"JOIN learning_materials lm USING(material_id) WHERE {enrolled} "
                    "ORDER BY attachment_id", (student_id,)
                )
                result["attachment_chunks"] = rows(
                    f"SELECT ac.*, f.filename, lm.course_id FROM attachment_chunks ac "
                    f"JOIN attachments f USING(attachment_id) "
                    f"JOIN learning_materials lm USING(material_id) WHERE {enrolled} "
                    "ORDER BY ac.chunk_id", (student_id,)
                )
                result["submissions"] = rows(
                    "SELECT s.student_id, s.assignment_id, a.course_id, a.title, "
                    "s.submitted_at, s.status, s.score_published, "
                    "CASE WHEN s.score_published = 1 THEN s.score END AS score, "
                    "CASE WHEN s.score_published = 1 THEN s.score_note END AS score_note "
                    "FROM submissions s JOIN assignments a USING(assignment_id) "
                    "WHERE s.student_id = ? ORDER BY s.assignment_id", (student_id,)
                )
                result["attendance_records"] = rows(
                    "SELECT * FROM attendance_records WHERE student_id = ? ORDER BY checkin_at, attendance_id",
                    (student_id,),
                )
                result["quiz_attempts"] = rows(
                    "SELECT a.student_id, a.quiz_id, q.course_id, q.title, a.attempt_no, "
                    "a.submitted_at, a.submission_method, a.score_published, "
                    "CASE WHEN a.score_published = 1 THEN a.score END AS score "
                    "FROM quiz_attempts a JOIN quizzes q USING(quiz_id) "
                    "WHERE a.student_id = ? ORDER BY a.quiz_id, a.attempt_no", (student_id,)
                )
                result["student_grade_items"] = rows(
                    "SELECT grade_item_id, student_id, course_id, category_id, source_type, source_id, "
                    "title, item_type, weight_percent, score_published, "
                    "CASE WHEN score_published = 1 THEN score END AS score, "
                    "CASE WHEN score_published = 1 THEN actual_score END AS actual_score "
                    "FROM student_grade_items WHERE student_id = ? ORDER BY grade_item_id", (student_id,)
                )
                result["student_course_grades"] = rows(
                    "SELECT student_id, course_id, published, "
                    "CASE WHEN published = 1 THEN final_grade END AS final_grade, "
                    "CASE WHEN published = 1 THEN raw_grade END AS raw_grade "
                    "FROM student_course_grades WHERE student_id = ? ORDER BY course_id", (student_id,)
                )
                return result
        except sqlite3.Error as exc:
            raise DataError(f"資料庫結構或查詢有誤，需使用本專案的學生端 schema：{exc}") from exc


def serialize_snapshot(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
