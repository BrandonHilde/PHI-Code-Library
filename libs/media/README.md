# medialib

Sound and video files in, samples and pictures out. It reads the bytes a program gives it; playing
the samples and showing the pictures are the program's (PHI OS's browser plays `<audio>` and
`<video>` with it, through weblib's `page/media.phi`). Its arithmetic is in whole numbers, worked
out from tables made once (from `Float`'s fdlibm functions, the same to the bit everywhere): PHI OS
runs on an emulated x86 whose floating point is slow.

```phi
use medialib;

call MediaLib.Start;
ptr<MdMedia> m: (MdMedia.Open: bytes length);      # finds the format from the bytes
if m is 0
	log 'not one I can read: ' MdMedia.error '\n';
	return;
;;
while (m.ReadAudio) > 0                            # m.frames of left and right in m.pcm, at m.rate
	...                                            # m.audio_us is when the first of them plays
;;
# a video's frames: each packet to the decoder, in order
ptr<MdVp8> d: (MdVp8.New);
while u32 k: 0; k < m.vcount; k++;
	ptr<MdPacket> p: m.vpackets + k * sizeof MdPacket;
	if (d.Decode: m.data + p.pos p.size) is 1      # 1: a picture to show, at p.us
		call d.ToArgb: pixels;                     # d.w by d.h of 0xAARRGGBB
	;;
;;
call MdVp8.Free: d;
call MdMedia.Close: m;
```

## What it reads

| Format | Codec | Checked against | Result (2026-11-23) |
|---|---|---|---|
| MP3 (MPEG-1, 2 and 2.5 Layer III) | | Apple's decoder (`afconvert`), `tools/media/check_mp3.py` | MDN's `t-rex-roar.mp3`: every sample within 1 of Apple's (82 dB), the same length, gapless (LAME's delay and padding) |
| WAV | PCM 8, 16, 24, 32 bits, float | made by the test | as made |
| WebM (Matroska) | VP8 video | libvpx, through Brave's WebCodecs, `tools/media/vp8_reference.py` | MDN's `flower.webm` (960x540, 150 frames): every frame's Y, U and V the same to the bit |
| MP4 | H.264 video (High profile and below: 8-bit 4:2:0 frames, CABAC and CAVLC, I, P and B with B pyramids, direct prediction spatial and temporal, weighted prediction explicit and implicit, 8x8 transforms, scaling matrices, long-term references) | Brave's WebCodecs, `tools/media/h264_reference.py` | MDN's `flower.mp4` (960x540, 150 frames, High 3.1, 8 references): every frame's Y, U and V the same to the bit, in the order shown (2026-11-23) |
| WebM, Ogg | Vorbis | Brave's WebCodecs (`tools/media/audio_reference.py`) | Commons recordings: every sample within 1 (11025 and 22050 Hz mono; 44100 Hz stereo piano, 45 s: 80.6 dB) or 4 (48000 Hz stereo, 74 dB) |
| MP4, M4A | AAC Low Complexity | Apple's decoder | Apple-encoded music (128 kbit/s stereo and 32 kbit/s mono): 79 and 81 dB, within 6 and 3, gapless (iTunes's iTunSMPB); a made clip of attacks and hiss (64 kbit/s, short windows, TNS): 76 dB, within 18 in one frame of attacks |

The everyday test (`test_media`) checks VP8 and H.264 to the bit, MP3's length and samples, and
Vorbis and AAC against those references (`tests/media/*.ref.raw`).

Also checked to the bit (2026-11-23, `tools/media/make_h264_test.py`): Baseline streams (CAVLC,
Chromium's OpenH264 encoder) at 320x240, 1280x720 and 330x186; High and Main streams from Apple's
hardware encoder at 320x240, 1280x720 and 250x150, and at a low bitrate. Not checked: CAVLC with 8x8
transforms, scaling matrices, long-term references, several slices to a picture (the encoders at hand
make none of these).

Not yet: Opus, VP9, AV1, FLAC; H.264's interlacing (fields, MBAFF), 4:2:2, 4:4:4 and more than 8 bits,
and Baseline's slice groups (FMO); HE-AAC's SBR and PS (it plays its core, at half its rate);
fragmented MP4.

## API

| Name | What it is |
|---|---|
| `MediaLib.Start` | Call once, before anything else. `MediaLib.VERSION` is 1 |
| `MdMedia.Open: data length` → | A `ptr<MdMedia>` for the file, or 0 with the reason in `MdMedia.error`. The bytes must stay as they are until `Close` |
| `MdMedia.Close: m` | Lets it go |
| `MdMedia` | `format` (`MdMedia.MP3`, `WAV`, `WEBM`, `OGG`, `MP4`), `duration_us` (-1 if it can't tell); sound: `has_audio`, `codec`, `rate`, `channels`; video: `has_video`, `vcodec` (`MdMedia.CODEC_VP8`), `width`, `height`, and its packets `vpackets` (`vcount` of `MdPacket`: `pos`, `size`, `us`, `flags` with `MdMedia.KEY` for a key frame) |
| `m.ReadAudio` → | Decodes the next sound: frames (0 at the end) into `m.pcm`, 16-bit left and right, `m.frames` of them, from `m.audio_us` |
| `m.SeekAudio: us` | The next `ReadAudio` starts at about that time |
| `MdMedia.Decodes: codec` → | Whether medialib decodes a codec (a container's track of one it doesn't is passed over) |
| `MdVp8.New` → / `MdVp8.Free: d` | A VP8 decoder, which keeps the frames a stream's next frames are made from |
| `d.Decode: frame length` → | 1: a picture (`d.out_y`, `out_u`, `out_v`, rows `d.ys` and `d.uvs` apart, `d.w` by `d.h`); 0: a frame not to show; -1: `MdVp8.error` says why |
| `d.ToArgb: pixels` | The picture as `0xAARRGGBB` (BT.601, as libwebp converts) |
| `MdVideo.Open: m` → / `MdVideo.Free: v` | A decoder for `m`'s video, whatever its codec (VP8, H.264), or 0 (`MdMedia.error`) |
| `v.Decode: packet` → | A packet of `m.vpackets`, in order: how many pictures are ready, or -1 |
| `v.Peek` → / `v.Take` → | Whether a picture is ready (shown at `v.ahead_us`); taking it: `v.out_y`, `out_u`, `out_v`, rows `v.ys` and `v.uvs` apart, `v.w` by `v.h`, shown at `v.us`, good until the next `Decode`. Pictures come in the order they're shown |
| `v.Flush` / `v.Reset` | After the last packet (what the decoder holds back is ready) / before a seek (it goes on from a key frame) |
| `v.ToArgb: pixels` | The picture taken as `0xAARRGGBB`, by the stream's colours (BT.709 or BT.601, video or full range) |
| `MdH264.New` → / `d.Configure: avcc length` → / `d.Decode: sample length us` → / `d.Take` → | An H.264 decoder by itself (no avcC: Annex B start codes) |
| `MdMp3.New` → / `d.Frame: data length` → | An MP3 decoder by itself: one frame to `d.pcm` (`d.channels` interleaved, `d.rate`) |

| `MdVorbis.New` → / `d.Header: packet length` → / `d.Decode: packet length` → | A Vorbis decoder by itself: its three headers, then audio packets into `d.pcm` |
| `MdAac.New` → / `d.Config: asc length` → / `d.Decode: block length` → | An AAC decoder by itself: its AudioSpecificConfig, then raw data blocks into `d.pcm` (1024 frames) |

Everything else (`MdMp3Math`, `MdMp3Tables`, `MdMp3Bands`, `MdWebm`, `MdOgg`, `MdMp4`, `MdMdct`,
`MdVp8Tables`, `MdVp8Bool`, `MdVp8Frame`, `MdVp8Mb`, `MdVorbisTables`, `MdVorbisBook`, `MdVorbisFloor`,
`MdVorbisResidue`, `MdVorbisMapping`, `MdAacTables`, `MdH264Tables`, `MdH264Bits`, `MdH264Cabac`,
`MdH264Sps`, `MdH264Pps`, `MdH264Pic`, `MdH264Rec`, `MdH264Loop`, `MdH264Cavlc`) is how it works, and
may change.

## Where things come from

- MP3's Huffman codes and synthesis window: PDMP3's source (public domain), read by
  `tools/media/mp3_tables.py`, which checks every table is a whole prefix code of the values it
  should hold.
- VP8: a key frame is imagelib's decoder (`../image/imagelib/vp8.phi`, its shared methods copied in
  `medialib/vp8.phi`); the frames between follow RFC 6386's reference decoder, its tables copied from
  the RFC, and libvpx where the two differ (a loop filter delta that isn't sent keeps its value).
- Vorbis's floor table: the Vorbis I specification, by `tools/media/vorbis_tables.py`.
- AAC's Huffman codebooks and scalefactor bands: the PacketVideo AAC decoder in Android's source
  (Apache 2.0), by `tools/media/aac_tables.py`, which works each codeword out by doing what its
  decoding functions do (its tables are in a layout of its own) and checks each book is whole.
- H.264: written from the standard (ITU-T H.264, 2024 edition's equations); its tables (CABAC's
  contexts, ranges and states, the scans, normAdjust, the loop filter's alpha, beta and tc0, the
  default scaling lists) from openh264 (Cisco, BSD 2-clause) by `tools/media/h264_tables.py`, which
  checks each against values the standard gives.
- `tests/media`: MDN's CC0 example files (`flower.webm`, `flower.mp4`, `t-rex-roar.mp3`), a CC0 recording from
  Wikimedia Commons (`philosophy.oga`), and an AAC clip made here (`tools/media/make_aac_test.py`).
