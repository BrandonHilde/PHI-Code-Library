// For check_svg.py: draws a scene with macOS's own Quartz (CoreGraphics), as the reference vectorlib
// is compared with. Paths come already absolute (M, L, C, Z: check_svg.py reads SVG's path data and
// turns arcs and quadratics into cubics itself), so this is Quartz's filling, outlining, gradients and
// transforms, on its own terms.
//     swiftc -O quartz.swift -o quartz;  quartz SCENE OUT    (OUT: W * H pixels of R G B A, on white)
import Foundation
import CoreGraphics

let args = CommandLine.arguments
let text = try! String(contentsOfFile: args[1], encoding: .utf8)
let space = CGColorSpace(name: CGColorSpace.sRGB)!
var w = 64, h = 64
var ctx: CGContext! = nil
var matrix = CGAffineTransform.identity
var color = CGColor(red: 0, green: 0, blue: 0, alpha: 1)
var gradKind = ""
var gradNums: [CGFloat] = []
var gradStops: [(CGFloat, CGColor)] = []
var path = CGMutablePath()
var dashPhase: CGFloat = 0
var dashes: [CGFloat] = []

func hexColor(_ s: String) -> CGColor {
    let v = UInt32(s.dropFirst(2), radix: 16)!
    return CGColor(colorSpace: space, components: [CGFloat((v >> 16) & 255) / 255, CGFloat((v >> 8) & 255) / 255,
                                                    CGFloat(v & 255) / 255, CGFloat(v >> 24) / 255])!
}

func drawGradient() {
    let g = CGGradient(colorsSpace: space, colors: gradStops.map { $0.1 } as CFArray, locations: gradStops.map { $0.0 })!
    let n = gradNums
    if gradKind == "linear" {
        ctx.drawLinearGradient(g, start: CGPoint(x: n[0], y: n[1]), end: CGPoint(x: n[2], y: n[3]),
                               options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    } else {
        ctx.drawRadialGradient(g, startCenter: CGPoint(x: n[3], y: n[4]), startRadius: 0,
                               endCenter: CGPoint(x: n[0], y: n[1]), endRadius: n[2],
                               options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    }
}

for raw in text.split(separator: "\n") {
    let p = raw.split(separator: " ").map(String.init)
    if p.isEmpty { continue }
    let f = p.dropFirst().compactMap { Double($0) }.map { CGFloat($0) }
    switch p[0] {
    case "size":
        w = Int(f[0]); h = Int(f[1])
        ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4, space: space,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
        ctx.translateBy(x: 0, y: CGFloat(h))
        ctx.scaleBy(x: 1, y: -1)
    case "matrix":
        matrix = CGAffineTransform(a: f[0], b: f[1], c: f[2], d: f[3], tx: f[4], ty: f[5])
    case "color":
        color = hexColor(p[1]); gradKind = ""
    case "linear", "radial":
        gradKind = p[0]; gradNums = f; gradStops = []
    case "stop":
        gradStops.append((f[0], hexColor(p[2])))
    case "path":
        path = CGMutablePath()
    case "M": path.move(to: CGPoint(x: f[0], y: f[1]))
    case "L": path.addLine(to: CGPoint(x: f[0], y: f[1]))
    case "C": path.addCurve(to: CGPoint(x: f[4], y: f[5]), control1: CGPoint(x: f[0], y: f[1]), control2: CGPoint(x: f[2], y: f[3]))
    case "Z": path.closeSubpath()
    case "dash":
        dashPhase = f[0]; dashes = Array(f.dropFirst())
    case "fill":
        ctx.saveGState()
        ctx.concatenate(matrix)
        ctx.addPath(path)
        let rule: CGPathFillRule = f[0] == 1 ? .evenOdd : .winding
        if gradKind == "" {
            ctx.setFillColor(color)
            ctx.fillPath(using: rule)
        } else {
            ctx.clip(using: rule)
            drawGradient()
        }
        ctx.restoreGState()
    case "stroke":
        ctx.saveGState()
        ctx.concatenate(matrix)
        ctx.setLineWidth(f[0])
        ctx.setLineJoin([CGLineJoin.miter, .round, .bevel][Int(f[1])])
        ctx.setLineCap([CGLineCap.butt, .round, .square][Int(f[2])])
        ctx.setMiterLimit(f[3])
        if !dashes.isEmpty { ctx.setLineDash(phase: dashPhase, lengths: dashes) }
        ctx.addPath(path)
        if gradKind == "" {
            ctx.setStrokeColor(color)
            ctx.strokePath()
        } else {
            ctx.replacePathWithStrokedPath()
            ctx.clip()
            drawGradient()
        }
        ctx.restoreGState()
    default:
        break
    }
}
let data = ctx.data!.assumingMemoryBound(to: UInt8.self)
let out = Data(bytes: data, count: w * h * 4)
try! out.write(to: URL(fileURLWithPath: args[2]))
