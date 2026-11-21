// For make_woff2_tests.py: what macOS's CoreText makes of a font file, glyph by glyph, to show that
// a WOFF2 file holds the same font as the font it was made from. CoreText reads WOFF2 itself.
//     swiftc -O coretext_glyphs.swift -o coretext_glyphs;  coretext_glyphs FONT
// prints units per em and the glyph count, then each glyph's advance and bounding box in font units
// (at a size of one em), and how many parts its outline has.
import Foundation
import CoreText

let data = try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
guard let desc = CTFontManagerCreateFontDescriptorFromData(data as CFData) else {
    print("CoreText can't read it")
    exit(1)
}
let probe = CTFontCreateWithFontDescriptor(desc, 12, nil)
let upem = CGFloat(CTFontGetUnitsPerEm(probe))
let font = CTFontCreateWithFontDescriptor(desc, upem, nil)
let count = CTFontGetGlyphCount(font)
print("units \(Int(upem)) glyphs \(count)")
var glyphs = (0..<count).map { CGGlyph($0) }
var advances = [CGSize](repeating: .zero, count: count)
var boxes = [CGRect](repeating: .zero, count: count)
CTFontGetAdvancesForGlyphs(font, .horizontal, &glyphs, &advances, count)
CTFontGetBoundingRectsForGlyphs(font, .horizontal, &glyphs, &boxes, count)
for i in 0..<count {
    var parts = 0
    if let path = CTFontCreatePathForGlyph(font, glyphs[i], nil) {
        path.applyWithBlock { _ in parts += 1 }
    }
    let b = boxes[i]
    print("\(i) \(Int(advances[i].width.rounded())) \(Int(b.minX.rounded())) \(Int(b.minY.rounded())) \(Int(b.maxX.rounded())) \(Int(b.maxY.rounded())) \(parts)")
}
