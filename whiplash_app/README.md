# Whiplash Gag App (iOS / Swift)

Entertainment-only iOS app. Core Motion detects a sudden whiplash-style jerk,
then plays a whip-crack sound and a shake/flash animation. Cooldown prevents
repeat-triggering; a slider adjusts sensitivity.

## Setup
1. Xcode → New Project → iOS App (SwiftUI), name `Whiplash`.
2. Delete the generated `*App.swift` / `ContentView.swift`, then drag in the files from `Sources/`.
3. Add a `whip.mp3` to the bundle (optional; falls back to a system sound).
4. Run on a **real device**. The simulator has no motion sensors.

## Next
- Multiple sound packs
- Shareable video capture of the reaction
- Tune thresholds in `WhiplashDetector.swift` on-device
