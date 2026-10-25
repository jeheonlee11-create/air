# Website demo media kit — $0, recorded from the real local demo

Nothing here is fabricated: every shot uses the existing local demo (`demo/app.py`) or the
public site, both running on real data from public log `75957ba9`. No paid tools: record
with **QuickTime Player (File → New Screen Recording)** or `screencapture -v` — both ship
with macOS. Target: 60–90 s, 1920×1080, ≤10 MB output via HandBrake (free) or
`ffmpeg` if installed; otherwise upload the raw .mov (Cloudflare Pages serves it fine, but
prefer compressed).

## 60–90 second website demo script (voiceover + captions in demo_captions.vtt)

| # | Shot (see shot list) | Voiceover |
|---|---|---|
| 1 | Site hero, trace draws in | "This is a real drone crash — a public flight log anyone can download. The owner's entire analysis was one sentence: 'my drone started to gain altitude sharply.'" |
| 2 | Local demo: click "Run the sample crash instead" | "Drop that log into AIR. Under a second later, it's an incident record." |
| 3 | Record page: chips + findings scroll | "Seven findings, each typed: measured evidence, the threshold it tripped, and where that threshold comes from. Battery hit zero percent — while it was still flying." |
| 4 | Conformance table close-up | "AIR checked the flight against written procedures. Height limit 120 meters above launch: the flight hit 121.57, past the one-meter measurement tolerance. Stating the tolerance is the point — records get challenged." |
| 5 | Altitude chart, conflict annotation | "Two independent altitude sensors disagree by twenty meters at the crash. AIR doesn't pick a winner — it reports the conflict, so nobody builds a case on the wrong number." |
| 6 | Click "Verify record now", PASS output | "And the whole record is sealed: hash tree, signature, offline verifier. Change one byte, verification fails." |
| 7 | Site limitations section | "It's early: PX4 logs only, a 100-log public evaluation, every limitation published." |
| 8 | CTA section | "If you investigate real incidents, bring one log and twenty minutes. air.findanything.dev." |

## Shot list
1. `http://127.0.0.1:8421/` hero — reload page, let the trace animate (2.8 s), hold 3 s.
2. `http://127.0.0.1:8420/` — cursor to "Run the sample crash instead", click, processing → record page (~2 s real time; don't cut — the speed is the demo).
3. Record page: slow scroll from chips through the first three finding cards.
4. Zoom (⌘+ once) on the conformance table rows ALT-1 FAIL / BAT-1 FAIL.
5. Site crash section: hold on altitude chart; move mouse along scrubber slowly.
6. Record page: click "Verify record now"; hold on VERIFICATION PASSED (exit 0) 3 s.
7. Site: scroll limitations grid, steady pace, 4 s.
8. Site: CTA section, end on the mailto button. Cut.

## Poster frame
`site/src/assets/img/poster.png` (1280×720, generated from real data by
`site/tools/gen_images.py`) — use as the `<video poster>` and as the YouTube/social thumbnail.

## Captions
`site/media/demo_captions.vtt` — WebVTT, timed to the 8 beats above at a 75-second read.
Adjust timestamps after recording to match your actual cut.

## Static fallback (already shipping)
The site itself is the no-video experience: the crash section presents the same story as
stills + interactive scrubber, and works with JavaScript disabled. If a `<video>` is added
later, wrap it so the existing SVG remains the `prefers-reduced-motion` and no-JS state,
with WebM+MP4 sources and the poster above. **Do not add the video element until a real
recording exists — no placeholder players.**
