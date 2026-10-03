import CoreMotion
import Foundation

/// Watches device motion and fires `onWhiplash` when rotation rate or
/// acceleration spikes past the sensitivity threshold. A cooldown stops
/// continued shaking from re-triggering.
final class WhiplashDetector: ObservableObject {
    /// 0...1, higher = triggers more easily.
    @Published var sensitivity: Double = 0.5
    @Published private(set) var isRunning = false

    var onWhiplash: (() -> Void)?

    private let motion = CMMotionManager()
    private let queue = OperationQueue()
    private let cooldown: TimeInterval = 1.5
    private var lastTrigger = Date.distantPast

    // Thresholds at sensitivity 0 (hard) and 1 (easy).
    private var rotationThreshold: Double { 12.0 - sensitivity * 8.0 }   // rad/s
    private var accelThreshold: Double { 4.0 - sensitivity * 2.5 }       // g (user accel)

    func start() {
        guard motion.isDeviceMotionAvailable, !motion.isDeviceMotionActive else { return }
        motion.deviceMotionUpdateInterval = 1.0 / 60.0
        motion.startDeviceMotionUpdates(to: queue) { [weak self] data, _ in
            guard let self, let data else { return }
            let r = data.rotationRate
            let rotation = sqrt(r.x * r.x + r.y * r.y + r.z * r.z)
            let a = data.userAcceleration
            let accel = sqrt(a.x * a.x + a.y * a.y + a.z * a.z)
            guard rotation > self.rotationThreshold || accel > self.accelThreshold else { return }
            self.trigger()
        }
        isRunning = true
    }

    func stop() {
        motion.stopDeviceMotionUpdates()
        isRunning = false
    }

    private func trigger() {
        let now = Date()
        guard now.timeIntervalSince(lastTrigger) > cooldown else { return }
        lastTrigger = now
        DispatchQueue.main.async { self.onWhiplash?() }
    }
}
