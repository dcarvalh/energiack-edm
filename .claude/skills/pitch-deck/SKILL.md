---
name: pitch-deck
description: Rules for openEDM's pitch deck (prototype/pitch/, French index.html + English en.html) and for recording the pitch video and app clips with tools/record_video.py. Use before editing either deck or its clips, or recording a video.
---

# Pitch deck and pitch video

- Pitch video: `.venv/bin/python tools/record_video.py --lang fr` (storyboard = `SHOTS` in that file; output in the
  git-ignored `video-out/`). The recorder captures the browser's frames over CDP because Playwright's own
  recorder is limited to the CSS viewport size.
- **Pitch deck** = `prototype/pitch/index.html` (French), live at `/pitch/`, and its English copy `en.html` (15 Nov,
  same clips with French app text: change both decks together; README › Pitch deck). Decided 14 Nov: French,
  silent, light, clicked through live; a title slide (not numbered) + 6 slides, one `<section class="slide">` each;
  short text (summarise, cut minor bullets); app clips only where the storyboard asks for one; slide 1's animations
  play once, clips loop. The folder must stay self-contained (own `fonts/`, `clips/`, no `../` URL) so it opens from
  disk offline: test with the network off. Clips (16:9 when two are stacked, 4:3 alone) are the only media committed;
  record `access` on the server version with `--url` and the demo logins. The Geneva map renders at about 3 fps on a machine
  without a GPU, so its recording (sped up 4x) is a little jerky. Do not "repair" it with ffmpeg frame blending
  (`minterpolate`): tried on 14 Nov, David judged the result worse and it was reverted. A truly smooth clip needs a
  recording on a machine with a GPU. Headless Chromium cannot play H.264: a
  screenshot shows the poster frame, so say clips were not seen playing. "Energo" and the team's first names are
  allowed on the deck (David, 14 Nov).
