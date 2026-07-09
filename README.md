# Sprite Motion Reducer

把短角色動作影片或 GIF 轉成低幀數 Sprite Sheet，並輸出 Unity 可用的每幀播放時間資料。

## HTML 版

直接用瀏覽器打開 `index.html`：

```powershell
start .\index.html
```

HTML 版功能：

- 選擇瀏覽器可解碼的影片，例如 `.mp4`、`.webm`。
- 依 Sample FPS 擷取 raw frames。
- 顯示全 frame 四欄縮圖網格。
- 手動勾選要匯出的 frame，旁邊即時預覽動態播放與 Sprite Sheet。
- `Sheet Columns` 控制 Sprite Sheet 排版；Rows 會依已選 frame 數自動計算。
- Sprite Sheet 每格會顯示預設勾選的 checkbox；取消勾選只會先從 Animation Preview 排除，圖片仍留在 Sheet 上。
- 使用 `Delete Unselected Frames` 才會真正移除未勾選圖片，並同步右側 Select Frames。
- Animation Preview 有 Play/Pause、Prev 與進度 slider；播放到的 frame 會在 Sprite Sheet 上以金色高亮。
- Sprite Sheet canvas 可聚焦，選中某格後按 Enter 或 Space 可移除該 frame。
- `Scale Mode` 可選 `Contain`、`Cover`、`Stretch`；預設 `Contain` 會保持原始比例，不會壓扁。
- `Preview Speed` 只調整畫面上的動態預覽速度，不改匯出的 `duration_ms`。
- 可用 `Auto Suggest` 依 RGB / Alpha 差異先自動建議，再手動微調。
- 匯出只包含已勾選 frame 的 Sprite Sheet PNG。
- 匯出只包含已勾選 frame 的 `unity_timing.json`。
- 匯出只包含已勾選 frame 的 `keyframe_report.md`。

限制：

- 純單檔 HTML 版暫不穩定支援多幀 GIF 解析。
- 暫不輸出 animated GIF 檔案；可用畫面上的 timeline 和下載的 JSON 檢查節奏。

## Python CLI 版

## 安裝

```powershell
python -m pip install -r requirements.txt
```

## 使用

```powershell
python sprite_motion_reducer.py attack_01.mp4 --target 16 --grid 4 4 --size 256 256 --output ./output/attack_01
```

常用參數：

- `--target 9|16|24|32`：目標關鍵幀數。
- `--grid COLUMNS ROWS`：Sprite Sheet 欄列，例如 `4 4`。
- `--size WIDTH HEIGHT`：每格輸出尺寸；不指定則使用原影片尺寸。
- `--loop`：Loop 動畫，不強制保留最後一幀。
- `--fps 30`：影片 FPS 讀取錯誤時手動覆蓋。
- `--lock 0,8,15`：指定必定保留的來源幀。
- `--exclude 12,13`：指定不要選取的來源幀。
- `--strategy diff|average`：使用差異分析或平均抽幀。
- `--padding 2`：Sprite Sheet 每格間距。

## 輸出

- `raw_frames/frame_0000.png...`：原始擷取幀。
- `reduced_sheet_4x4.png`：精簡後 Sprite Sheet。
- `preview_original.gif`：原始節奏預覽。
- `preview_reduced.gif`：精簡後變速預覽。
- `unity_timing.json`：Unity timing metadata。
- `keyframe_report.md`：關鍵幀選取報告。

## 演算法 v0.1

目前使用規格書中的 MVP 簡化版：

```text
importance_score = RGB 差異 * 0.7 + Alpha 差異 * 0.3，再混入差異變化量
```

工具會保留第一幀、非 Loop 動畫的最後一幀、手動鎖定幀，並用 `minimum_distance = raw_frame_count / target / 2` 避免關鍵幀過度集中。

每張精簡幀的 `duration_ms` 依來源幀的 midpoint 區間計算，讓總播放長度接近原始影片。
