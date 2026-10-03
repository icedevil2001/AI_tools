import SwiftUI
import AVFoundation

struct ContentView: View {
    @StateObject private var detector = WhiplashDetector()
    @State private var shake = 0
    @State private var flash = false
    @State private var player: AVAudioPlayer?

    var body: some View {
        ZStack {
            (flash ? Color.red : Color.black).ignoresSafeArea()
            VStack(spacing: 24) {
                Text(flash ? "💥" : "🤕")
                    .font(.system(size: 120))
                    .modifier(Shake(animatableData: CGFloat(shake)))
                Text("Whip your phone")
                    .font(.title2).foregroundStyle(.white)
                VStack {
                    Text("Sensitivity").foregroundStyle(.white.opacity(0.7))
                    Slider(value: $detector.sensitivity)
                }
                .padding(.horizontal, 40)
            }
        }
        .onAppear {
            detector.onWhiplash = { react() }
            detector.start()
        }
        .onDisappear { detector.stop() }
    }

    private func react() {
        playSound()
        withAnimation(.linear(duration: 0.5)) { shake += 1 }
        flash = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { flash = false }
    }

    /// Add `whip.mp3` to the app bundle. Falls back to a system sound if missing.
    private func playSound() {
        if let url = Bundle.main.url(forResource: "whip", withExtension: "mp3"),
           let p = try? AVAudioPlayer(contentsOf: url) {
            player = p
            p.play()
        } else {
            AudioServicesPlaySystemSound(1105)
        }
    }
}

struct Shake: GeometryEffect {
    var animatableData: CGFloat
    func effectValue(size: CGSize) -> ProjectionTransform {
        let x = 20 * sin(animatableData * .pi * 8)
        return ProjectionTransform(CGAffineTransform(translationX: x, y: 0))
    }
}
