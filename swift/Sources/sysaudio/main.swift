// sysaudio: capture system audio via ScreenCaptureKit, write int16 mono PCM to stdout.
// Same on-stdout contract as audiotee, but uses SCK instead of Core Audio Process Tap.
// macOS 13+. Requires Screen Recording TCC permission (user-grantable, no admin).
//
// Usage: sysaudio [--sample-rate N]
//   --sample-rate  output sample rate in Hz (default 16000)

import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia

@available(macOS 13.0, *)
final class AudioCaptureHandler: NSObject, SCStreamDelegate, SCStreamOutput {
    private let stdout = FileHandle.standardOutput
    private let stderr = FileHandle.standardError
    private let outputSampleRate: Double

    init(outputSampleRate: Int) {
        self.outputSampleRate = Double(outputSampleRate)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid, sampleBuffer.numSamples > 0 else { return }

        var blockBufferOut: CMBlockBuffer?
        var ablPtr = AudioBufferList()
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: &ablPtr,
            bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &blockBufferOut
        )
        guard status == 0, let baseAddr = ablPtr.mBuffers.mData else { return }

        let byteCount = Int(ablPtr.mBuffers.mDataByteSize)
        let floatCount = byteCount / MemoryLayout<Float>.size
        let floatPtr = baseAddr.assumingMemoryBound(to: Float.self)

        // SCK delivers Float32 PCM. Convert to Int16 LE and write to stdout.
        var int16Bytes = [UInt8]()
        int16Bytes.reserveCapacity(floatCount * 2)
        for i in 0..<floatCount {
            var f = floatPtr[i]
            if f > 1.0 { f = 1.0 } else if f < -1.0 { f = -1.0 }
            let sample = Int16(f * 32767.0)
            int16Bytes.append(UInt8(truncatingIfNeeded: Int(sample) & 0xFF))
            int16Bytes.append(UInt8(truncatingIfNeeded: (Int(sample) >> 8) & 0xFF))
        }
        try? stdout.write(contentsOf: Data(int16Bytes))
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        write(stderr: "stream stopped with error: \(error)\n")
        exit(2)
    }

    private func write(stderr line: String) {
        if let d = line.data(using: .utf8) { stderr.write(d) }
    }
}

@available(macOS 13.0, *)
func run(sampleRate: Int) async throws {
    let stderr = FileHandle.standardError
    func log(_ s: String) {
        if let d = (s + "\n").data(using: .utf8) { stderr.write(d) }
    }

    log("sysaudio: requesting shareable content...")
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
    guard let display = content.displays.first else {
        log("sysaudio: no displays found")
        exit(1)
    }
    log("sysaudio: using display \(display.displayID), \(content.applications.count) apps visible")

    // Filter: this display, no excluded apps, no excluded windows.
    // Audio-wise this captures ALL system audio.
    let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])

    let config = SCStreamConfiguration()
    config.capturesAudio = true
    config.sampleRate = sampleRate
    config.channelCount = 1
    config.excludesCurrentProcessAudio = true
    // SCK requires a video config even for audio-only. Use minimum and very slow frame rate.
    config.width = 2
    config.height = 2
    config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
    config.queueDepth = 5

    let handler = AudioCaptureHandler(outputSampleRate: sampleRate)
    let stream = SCStream(filter: filter, configuration: config, delegate: handler)

    let audioQueue = DispatchQueue(label: "sysaudio.audio", qos: .userInteractive)
    try stream.addStreamOutput(handler, type: .audio, sampleHandlerQueue: audioQueue)

    // Some SCK versions require a video output handler too even if we ignore frames.
    let videoQueue = DispatchQueue(label: "sysaudio.video", qos: .background)
    try stream.addStreamOutput(handler, type: .screen, sampleHandlerQueue: videoQueue)

    log("sysaudio: starting capture (sample rate \(sampleRate), mono int16 LE)")
    try await stream.startCapture()
    log("sysaudio: stream started, piping PCM to stdout")

    // Run forever; SIGTERM/SIGINT will exit the process.
    while true {
        try await Task.sleep(nanoseconds: 1_000_000_000)
    }
}

@available(macOS 13.0, *)
@main
struct SysAudio {
    static func main() async {
        var sampleRate = 16000
        var args = Array(CommandLine.arguments.dropFirst())
        while !args.isEmpty {
            let a = args.removeFirst()
            switch a {
            case "--sample-rate":
                if let n = args.first.flatMap(Int.init) { sampleRate = n; args.removeFirst() }
            case "-h", "--help":
                print("Usage: sysaudio [--sample-rate N]")
                print("  default: --sample-rate 16000")
                exit(0)
            default:
                FileHandle.standardError.write("unknown arg: \(a)\n".data(using: .utf8)!)
                exit(1)
            }
        }

        signal(SIGTERM, SIG_DFL)
        signal(SIGINT, SIG_DFL)

        do {
            try await run(sampleRate: sampleRate)
        } catch {
            FileHandle.standardError.write("sysaudio error: \(error)\n".data(using: .utf8)!)
            exit(1)
        }
    }
}
