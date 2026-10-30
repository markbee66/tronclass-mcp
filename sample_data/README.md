# TronClass 學生端課程資料庫（虛構資料）

這份資料庫以「一位學生在 TronClass 學生端能看到的資訊」為範圍，資料結構依實際學生端畫面整理；所有課程、人名、代碼、成績與紀錄皆為模擬資料。

## 核心原則

- 只存目前學生自己的私人資料，不包含其他學生的成績、點名或繳交紀錄。
- 課程共用資料與個人資料分開：公告、教材、作業等是課程共用；點名、繳交、作答、成績是目前學生自己的紀錄。
- 教材附件支援 PDF / PPTX / DOCX，資料庫同時保留附件中抽取後的文字與來源位置（頁碼 / 投影片 / 段落）。
- 原有的「公告改期、系統截止日未更新、討論區非官方資訊」情境保留，方便期中 System 1 做錯誤測試。

## 主要資料表

| 資料表 | 內容 |
|---|---|
| `courses` | 課程名稱、課程代碼、教務科目代碼、學年期、必選修、學分、開課系級、課程類型、起訖日、上課時間、進度 |
| `course_instructors` | 授課教師，可支援一門課多位教師 |
| `course_outline` | 課程簡介中/英文、完整資訊連結、評分方式、遲交規則、繳交方式 |
| `announcements` | 公告 |
| `assignments` | 作業名稱、活動時間、章節/單元、個人/分組、繳交方式 |
| `submissions` | 目前學生自己的繳交狀態、時間、成績、是否公布 |
| `learning_materials` | 教材活動名稱、活動時間、完成指標、頁面文字 |
| `attachments` | 教材附件檔名、PDF/PPTX/DOCX 類型、檔案大小、上傳時間 |
| `attachment_chunks` | 從附件抽出的文字，以及 page / slide / paragraph 位置 |
| `materials` | 原有講義 Markdown 切段資料，保留 `student / teacher_only` 權限 |
| `attendance_records` | 目前學生自己的點名時間、出席/請假/缺席、是否計分、來源（雷達/QR/數字） |
| `quizzes` | 線上測驗名稱、開放/截止時間、章節、滿分 |
| `quiz_attempts` | 目前學生自己的最後交卷時間、交卷方式、成績、是否公布 |
| `grade_categories` | 成績分類與配分比例 |
| `student_grade_items` | 目前學生各作業/測驗/點名的得分、比例、實際得分、是否公布 |
| `student_course_grades` | 課程總成績與原始成績（可未公布） |
| `discussions` | 討論區發言，屬非官方資訊來源 |

## 檔案

- `course.db`：SQLite 資料庫。
- `build_db.py`：可由 `data/` 重建資料庫。
- `data/`：原始 JSON / Markdown。
- `attachments/`：模擬 TronClass 教材附件。
- `all_data_for_prompt.md`：為了相容原專案保留的 System 1 純文字匯出；資料庫本身才是本次主要修改內容。

## 常用查詢範例

```python
import sqlite3
con = sqlite3.connect("course.db")

# 我的某門課點名紀錄
con.execute("""
SELECT checkin_at, status, score_setting, source
FROM attendance_records
WHERE student_id=? AND course_id=?
ORDER BY checkin_at DESC
""", ("S11200001", "C01")).fetchall()

# 我的作業狀態
con.execute("""
SELECT a.title, a.start_at, a.due, a.assignment_type,
       s.status, s.score, s.score_published
FROM assignments a
JOIN submissions s USING(assignment_id)
WHERE s.student_id=? AND a.course_id=?
""", ("S11200001", "C01")).fetchall()

# 教材附件與抽取文字
con.execute("""
SELECT lm.title, f.filename, f.file_type, c.locator_type, c.locator, c.content
FROM learning_materials lm
JOIN attachments f USING(material_id)
JOIN attachment_chunks c USING(attachment_id)
WHERE lm.course_id=?
""", ("C01",)).fetchall()

# 成績頁：各活動的得分、比例、實際得分
con.execute("""
SELECT g.title, g.item_type, g.score, g.weight_percent,
       g.actual_score, g.score_published
FROM student_grade_items g
WHERE g.student_id=? AND g.course_id=?
ORDER BY g.grade_item_id
""", ("S11200001", "C01")).fetchall()
```
