"""Build TronClass-like student-side mock SQLite database from data/."""
import json,re,sqlite3
from pathlib import Path
BASE=Path(__file__).parent; DATA=BASE/'data'; DB_PATH=BASE/'course.db'; PROMPT_PATH=BASE/'all_data_for_prompt.md'
def load(n): return json.loads((DATA/n).read_text(encoding='utf-8'))
SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE semester(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE no_class_days(date TEXT PRIMARY KEY,weekday TEXT,reason TEXT);
CREATE TABLE students(student_id TEXT PRIMARY KEY,name TEXT);
CREATE TABLE courses(
 course_id TEXT PRIMARY KEY,name TEXT NOT NULL,course_code TEXT,subject_code TEXT,academic_year TEXT,semester_no TEXT,
 required_elective TEXT,credits REAL,department_class TEXT,course_type TEXT,start_date TEXT,end_date TEXT,
 weekday TEXT,time TEXT,room TEXT,progress_percent REAL,ta TEXT,ta_email TEXT);
CREATE TABLE course_instructors(course_id TEXT REFERENCES courses(course_id),instructor_name TEXT,role TEXT DEFAULT '授課教師',PRIMARY KEY(course_id,instructor_name));
CREATE TABLE course_outline(course_id TEXT PRIMARY KEY REFERENCES courses(course_id),intro_zh TEXT,intro_en TEXT,info_url TEXT,grading_json TEXT,late_policy TEXT,submission TEXT);
CREATE TABLE announcements(announcement_id TEXT PRIMARY KEY,course_id TEXT REFERENCES courses(course_id),posted_at TEXT,author TEXT,title TEXT,content TEXT);
CREATE TABLE assignments(
 assignment_id TEXT PRIMARY KEY,course_id TEXT REFERENCES courses(course_id),title TEXT,start_at TEXT,due TEXT,unit_name TEXT,
 assignment_type TEXT,submission TEXT,note TEXT,grade_published INTEGER DEFAULT 0);
CREATE TABLE submissions(student_id TEXT REFERENCES students(student_id),assignment_id TEXT REFERENCES assignments(assignment_id),submitted_at TEXT,status TEXT,score REAL,score_published INTEGER DEFAULT 0,score_note TEXT,PRIMARY KEY(student_id,assignment_id));
CREATE TABLE learning_materials(material_id TEXT PRIMARY KEY,course_id TEXT REFERENCES courses(course_id),title TEXT,start_at TEXT,end_at TEXT,completion_rule TEXT,body_text TEXT);
CREATE TABLE materials(chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,course_id TEXT REFERENCES courses(course_id),source TEXT,section TEXT,content TEXT,visibility TEXT DEFAULT 'student');
CREATE TABLE attachments(attachment_id TEXT PRIMARY KEY,material_id TEXT REFERENCES learning_materials(material_id),filename TEXT,file_type TEXT,file_size_bytes INTEGER,uploaded_at TEXT,local_path TEXT);
CREATE TABLE attachment_chunks(chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,attachment_id TEXT REFERENCES attachments(attachment_id),locator_type TEXT,locator TEXT,content TEXT);
CREATE TABLE discussions(post_id INTEGER PRIMARY KEY AUTOINCREMENT,course_id TEXT REFERENCES courses(course_id),posted_at TEXT,author TEXT,content TEXT);
CREATE TABLE attendance_records(attendance_id TEXT PRIMARY KEY,student_id TEXT REFERENCES students(student_id),course_id TEXT REFERENCES courses(course_id),checkin_at TEXT,status TEXT,score_setting TEXT,source TEXT,note TEXT);
CREATE TABLE quizzes(quiz_id TEXT PRIMARY KEY,course_id TEXT REFERENCES courses(course_id),title TEXT,open_at TEXT,close_at TEXT,unit_name TEXT,max_score REAL);
CREATE TABLE quiz_attempts(student_id TEXT REFERENCES students(student_id),quiz_id TEXT REFERENCES quizzes(quiz_id),attempt_no INTEGER,submitted_at TEXT,submission_method TEXT,score REAL,score_published INTEGER,PRIMARY KEY(student_id,quiz_id,attempt_no));
CREATE TABLE grade_categories(category_id TEXT PRIMARY KEY,course_id TEXT REFERENCES courses(course_id),name TEXT,weight_percent REAL);
CREATE TABLE student_course_grades(student_id TEXT REFERENCES students(student_id),course_id TEXT REFERENCES courses(course_id),final_grade REAL,raw_grade REAL,published INTEGER,PRIMARY KEY(student_id,course_id));
CREATE TABLE student_grade_items(grade_item_id TEXT PRIMARY KEY,student_id TEXT REFERENCES students(student_id),course_id TEXT REFERENCES courses(course_id),category_id TEXT REFERENCES grade_categories(category_id),source_type TEXT,source_id TEXT,title TEXT,item_type TEXT,weight_percent REAL,score REAL,score_published INTEGER,actual_score REAL);
"""
def split_sections(text):
    chunks=[]; title='（開頭）'; buf=[]
    for line in text.splitlines():
        if re.match(r'^#{2,3} ',line):
            if ''.join(buf).strip(): chunks.append((title,'\n'.join(buf).strip()))
            title=line.lstrip('#').strip(); buf=[]
        else: buf.append(line)
    if ''.join(buf).strip(): chunks.append((title,'\n'.join(buf).strip()))
    return chunks
def course_of(fn):
    m=re.match(r'(C\d{2})_',fn); return m.group(1) if m else None
def build_db():
    if DB_PATH.exists(): DB_PATH.unlink()
    con=sqlite3.connect(DB_PATH); con.executescript(SCHEMA)
    cal=load('calendar.json')
    for k in ['school','semester','timezone','week1_monday','total_weeks','week_rule']:
        con.execute('INSERT INTO semester VALUES (?,?)',(k,str(cal[k])))
    con.execute('INSERT INTO semester VALUES (?,?)',('special_weeks',json.dumps(cal['special_weeks'],ensure_ascii=False)))
    for d in cal['no_class_days']: con.execute('INSERT INTO no_class_days VALUES (?,?,?)',(d['date'],d['weekday'],d['reason']))
    st=load('student_status.json'); con.execute('INSERT INTO students VALUES (?,?)',(st['student_id'],st['name']))
    for c in load('courses.json'):
        con.execute('INSERT INTO courses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
          c['course_id'],c['name'],c['course_code'],c['subject_code'],c['academic_year'],c['semester_no'],c['required_elective'],c['credits'],c['department_class'],c['course_type'],c['start_date'],c['end_date'],c['weekday'],c['time'],c['room'],c['progress_percent'],c['ta'],c['ta_email']))
        for n in c.get('instructors',[c['teacher']]): con.execute('INSERT INTO course_instructors VALUES (?,?,?)',(c['course_id'],n,'授課教師'))
        con.execute('INSERT INTO course_outline VALUES (?,?,?,?,?,?,?)',(c['course_id'],c['intro_zh'],c['intro_en'],c['info_url'],json.dumps(c['grading'],ensure_ascii=False),c['late_policy'],c['submission']))
    for a in load('assignments.json'):
        con.execute('INSERT INTO assignments VALUES (?,?,?,?,?,?,?,?,?,?)',(a['assignment_id'],a['course_id'],a['title'],a['start_at'],a['due'],a['unit_name'],a['assignment_type'],a['submission'],a['note'],int(a['grade_published'])))
    recs={r['assignment_id']:r for r in st['records']}
    for a in load('assignments.json'):
        r=recs.get(a['assignment_id'],{}); at=r.get('submitted_at'); score=r.get('score'); note=r.get('score_note')
        status='已繳' if at else '未繳'
        con.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?,?)',(st['student_id'],a['assignment_id'],at,status,score,int(bool(score is not None and a['grade_published'])),note))
    for a in load('announcements.json'): con.execute('INSERT INTO announcements VALUES (?,?,?,?,?,?)',(a['announcement_id'],a['course_id'],a['posted_at'],a['author'],a['title'],a['content']))
    for m in load('learning_materials.json'): con.execute('INSERT INTO learning_materials VALUES (?,?,?,?,?,?,?)',(m['material_id'],m['course_id'],m['title'],m['start_at'],m['end_at'],m['completion_rule'],m['body_text']))
    for folder,vis in [('materials','student'),('teacher_only','teacher_only')]:
        p=DATA/folder
        if not p.exists(): continue
        for f in sorted(p.glob('*.md')):
            text=f.read_text(encoding='utf-8')
            if text.startswith('---'): text=text.split('---',2)[2]
            for sec,content in split_sections(text): con.execute('INSERT INTO materials(course_id,source,section,content,visibility) VALUES (?,?,?,?,?)',(course_of(f.name),f.name,sec,content,vis))
    for x in load('attachments.json'):
        fp=BASE/x['local_path']; size=fp.stat().st_size if fp.exists() else 0
        con.execute('INSERT INTO attachments VALUES (?,?,?,?,?,?,?)',(x['attachment_id'],x['material_id'],x['filename'],x['file_type'],size,x['uploaded_at'],x['local_path']))
    # attachment_chunks imported if present
    if (DATA/'attachment_chunks.json').exists():
        for x in load('attachment_chunks.json'): con.execute('INSERT INTO attachment_chunks(attachment_id,locator_type,locator,content) VALUES (?,?,?,?)',(x['attachment_id'],x['locator_type'],x['locator'],x['content']))
    p=DATA/'discussions'
    if p.exists():
        for f in sorted(p.glob('*.md')):
            text=f.read_text(encoding='utf-8')
            for block in text.split('\n---\n')[1:]:
                m=re.search(r'\*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · (.+?)\*\*\n(.+)',block.strip(),re.S)
                if m: con.execute('INSERT INTO discussions(course_id,posted_at,author,content) VALUES (?,?,?,?)',(course_of(f.name),m.group(1),m.group(2),m.group(3).strip()))
    for r in load('attendance_records.json'): con.execute('INSERT INTO attendance_records VALUES (?,?,?,?,?,?,?,?)',(r['attendance_id'],r['student_id'],r['course_id'],r['checkin_at'],r['status'],r['score_setting'],r['source'],r['note']))
    for q in load('quizzes.json'): con.execute('INSERT INTO quizzes VALUES (?,?,?,?,?,?,?)',(q['quiz_id'],q['course_id'],q['title'],q['open_at'],q['close_at'],q['unit_name'],q['max_score']))
    for a in load('quiz_attempts.json'): con.execute('INSERT INTO quiz_attempts VALUES (?,?,?,?,?,?,?)',(a['student_id'],a['quiz_id'],a['attempt_no'],a['submitted_at'],a['submission_method'],a['score'],int(a['score_published'])))
    gb=load('gradebook.json')
    for c in gb['categories']: con.execute('INSERT INTO grade_categories VALUES (?,?,?,?)',(c['category_id'],c['course_id'],c['name'],c['weight_percent']))
    for g in gb['course_grades']: con.execute('INSERT INTO student_course_grades VALUES (?,?,?,?,?)',(g['student_id'],g['course_id'],g['final_grade'],g['raw_grade'],int(g['published'])))
    for g in gb['items']: con.execute('INSERT INTO student_grade_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(g['grade_item_id'],g['student_id'],g['course_id'],g['category_id'],g['source_type'],g['source_id'],g['title'],g['item_type'],g['weight_percent'],g['score'],int(g['score_published']),g['actual_score']))
    con.commit(); return con

def build_prompt_file(con):
    # Kept only for backward compatibility. Database is the source of truth.
    out=['# 學生端可見課程資料（虛構）\n']
    for row in con.execute('SELECT c.course_id,c.name,c.course_code,c.credits,c.required_elective,c.department_class,c.start_date,c.end_date,o.intro_zh FROM courses c JOIN course_outline o USING(course_id)'):
        out.append(f'## {row[0]} {row[1]}\n課程代碼：{row[2]}；學分：{row[3]}；{row[4]}；{row[5]}；期間：{row[6]} 至 {row[7]}\n{row[8]}')
    out.append('\n## 公告')
    for r in con.execute('SELECT posted_at,course_id,title,content FROM announcements ORDER BY posted_at'): out.append(f'- {r[0]}｜{r[1]}｜{r[2]}：{r[3]}')
    out.append('\n## 作業與我的繳交狀態')
    for r in con.execute('SELECT a.course_id,a.title,a.start_at,a.due,a.assignment_type,s.status,s.score,s.score_published FROM assignments a JOIN submissions s USING(assignment_id)'): out.append(f'- {r}')
    out.append('\n## 我的點名紀錄')
    for r in con.execute('SELECT course_id,checkin_at,status,score_setting,source FROM attendance_records ORDER BY checkin_at'): out.append(f'- {r}')
    out.append('\n## 線上測驗與我的作答')
    for r in con.execute('SELECT q.course_id,q.title,q.open_at,q.close_at,a.submitted_at,a.submission_method,a.score,a.score_published FROM quizzes q LEFT JOIN quiz_attempts a USING(quiz_id)'): out.append(f'- {r}')
    PROMPT_PATH.write_text('\n'.join(out)+'\n',encoding='utf-8')
if __name__=='__main__':
    con=build_db(); build_prompt_file(con)
    print('integrity:',con.execute('PRAGMA integrity_check').fetchone()[0])
    for t in ['courses','course_outline','course_instructors','assignments','submissions','announcements','learning_materials','materials','attachments','attendance_records','quizzes','quiz_attempts','grade_categories','student_grade_items']:
        print(t,con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
