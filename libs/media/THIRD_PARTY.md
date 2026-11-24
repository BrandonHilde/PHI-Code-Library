# What came from elsewhere

medialib's code is its own or this repository's (its VP8 key frames are imagelib's decoder), and
nothing in it came from GPL code. What came from elsewhere is fixed data, and test data.

## Data built into programs

| Where | What | From | License |
|---|---|---|---|
| `medialib/mp3tables.phi` | MP3's Huffman code trees (ISO/IEC 11172-3's, as the ISO reference decoder had them) and its synthesis window | PDMP3's `pdmp3.c` (github.com/technosaurus/PDMP3), its text read by `tools/media/mp3_tables.py` | Public domain (the Unlicense) |
| `medialib/vp8tables.phi` | VP8's key frame tables (imagelib's, from libwebp, checked against RFC 6386), and its inter frame tables: modes' and motion vectors' probabilities, partitions, the six-tap and bilinear filters | imagelib's `vp8tables.phi`; RFC 6386's reference decoder (`modemv_data.h`, `vp8_prob_data.h`, `predict.c`) | libwebp's BSD 3-clause license; the RFC's code is under Google's BSD license (its section 20.26) |

| `medialib/vorbistables.phi` | Vorbis's floor1_inverse_dB_table | The Vorbis I specification (xiph.org), read by `tools/media/vorbis_tables.py` | Xiph.Org's specification (the codec is free of licensing and patents) |
| `medialib/aactables.phi` | AAC's Huffman codebooks and scalefactor bands (ISO/IEC 14496-3's) | The PacketVideo AAC decoder (`hcbtables_binary.cpp`, `decode_huff_cw_binary.cpp`, `sfb.cpp`) in Android's source (android.googlesource.com/platform/frameworks/base, android-2.3.7_r1, media/libstagefright/codecs/aacdec), worked out by `tools/media/aac_tables.py` | Apache 2.0 (PacketVideo) |
| `medialib/h264tables.phi` | H.264's CABAC context initialisation (m, n), rangeTabLPS and state transitions, zigzag scans, 8x8 significance contexts, normAdjust, chroma QP, deblocking alpha/beta/tc0, default scaling lists (ITU-T H.264's tables) | openh264 (`codec/common/src/common_tables.cpp`, `codec/decoder/core/inc/wels_common_basis.h`, `codec/decoder/core/src/deblocking.cpp`, github.com/cisco/openh264), read by `tools/media/h264_tables.py` | BSD 2-clause (Cisco Systems) |

A program that plays VP8 carries these tables, so its notices should include libwebp's and RFC 6386's
(<https://www.rfc-editor.org/rfc/rfc6386>); one that plays H.264, openh264's BSD notice (Copyright (c)
2013, Cisco Systems).

## Test data

Read by the tests, never built into a program.

| Where | What | From | License |
|---|---|---|---|
| `tests/media/flower.webm` | A 5-second WebM, VP8 (960x540) and Vorbis | MDN's interactive examples (`interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.webm`) | CC0 |
| `tests/media/flower.mp4` | The same 5 seconds as MP4: H.264 High profile (960x540) and AAC | MDN's interactive examples (`.../media/cc0-videos/flower.mp4`) | CC0 |
| `tests/media/t-rex-roar.mp3` | A 2-second MP3, 128 kbit/s stereo | MDN's interactive examples (`.../media/cc0-audio/t-rex-roar.mp3`) | CC0 |
| `tests/media/philosophy.oga` | A spoken word, Ogg Vorbis, mono, 11025 Hz | Wikimedia Commons (`File:Philosophy.oga`) | CC0 |
| `tests/media/philosophy.ref.raw` | Its samples as Brave's WebCodecs decoded them | made by `tools/media/audio_reference.py` | (made here) |
| `tests/media/plucks.m4a`, `plucks.ref.raw` | Two seconds of AAC, and Apple's decoding of it | made by `tools/media/make_aac_test.py` | (made here) |
| `tests/media/flower.vp8.crcs` | libvpx's pictures of `flower.webm`, by CRC | made by `tools/media/vp8_reference.py` through Brave's WebCodecs | (made here) |
| `tests/media/flower.h264.crcs` | A browser's decoding of `flower.mp4`'s pictures, by CRC | made by `tools/media/h264_reference.py` through Brave's WebCodecs | (made here) |
| `tests/media/shapes.h264`, `shapes.h264.crcs` | A Baseline (CAVLC) stream, 330x186, 20 pictures of moving shapes, and its pictures by CRC | made by `tools/media/make_h264_test.py` (drawn by a script, encoded and decoded by Brave's WebCodecs) | (made here) |
