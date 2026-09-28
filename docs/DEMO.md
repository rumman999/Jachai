# Demo runbook

Two flows, one control case, a backup video. Nothing else goes on stage.

## Night before (on mobile data, not venue Wi-Fi)

- [ ] Railway: model **on** (`ENABLE_ML` unset or `true`), latest commit deployed.
- [ ] Phone on **mobile data**, Wi-Fi off: open `https://jachai-api-production.up.railway.app/health` → `status: ok`, `visual: ready`, `ocr: true`.
- [ ] Install the **release APK** (`android/app/build/outputs/apk/release/app-release.apk`); its baked-in URL is the Railway one.
- [ ] The three demo files are on the phone, in a Gallery album called **Demo**, and pinned on the server:
  ```
  python scripts/add_override.py demo/fake_video.mp4 red
  python scripts/add_override.py demo/hoax_screenshot.jpg red --hoax-id <id from data/hoaxes.json>
  python scripts/add_override.py demo/real_photo.jpg green
  ```
  Commit + push `backend/data/demo_overrides.json` so Railway has the pins.
- [ ] Run both flows 3 times in a row. All green? Record the backup video (below).
- [ ] Phone: Do Not Disturb on, brightness max, screen timeout 10 min, battery > 80%.

## Backup screen recording

Record both flows succeeding with the phone's built-in screen recorder (Xiaomi: Control Centre → Screen recorder) or over USB:
```
adb shell screenrecord --time-limit 120 /sdcard/jachai_demo.mp4
adb pull /sdcard/jachai_demo.mp4
```
Have it on the laptop, full-screen ready. If a live flow fails, don't debug on stage — play the video.

## 10 minutes before

```
cd backend
python scripts/prewarm.py --image demo/fake_video.mp4
```
Wait for `warm.`, then open Jachai once on the phone (the home screen should say ✓ Connected).

## On stage

| # | Say | Do | Expect |
|---|---|---|---|
| 1 | "This video is going round WhatsApp. Is it real?" | Gallery → Demo → **fake video** → Share → **Check with Jachai** | 🔴 **সম্ভবত ভুয়া / Likely fake**, frames checked |
| 2 | "Now a forwarded post in Bengali." | Gallery → Demo → **hoax screenshot** → Share → Jachai | 🔴 **পরিচিত গুজব / Known hoax**, with the fact-check |
| — | "And it doesn't cry wolf." (control) | Gallery → Demo → **real photo** → Share → Jachai | 🟢 **সম্ভবত আসল / Likely authentic** |
| + | "One tap to warn the group." | On the red screen tap **Share · শেয়ার** → WhatsApp | Verdict + fact text in the chat |

The floating bubble is **not** in the live demo; mention it verbally as the path for private posts.

## If something breaks

| Symptom | Do |
|---|---|
| Spinner > 10 s | The server always answers within 8 s. If not, it's the network: play the backup video. |
| "Can't reach the server" | Venue network. Switch phone to mobile data / hotspot, or play the backup video. |
| Wrong colour on a demo file | It wasn't pinned or Railway didn't redeploy: use the backup video, fix after. |
