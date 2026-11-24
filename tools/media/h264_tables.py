#!/usr/bin/env python3
"""Make libs/media/medialib/h264tables.phi: H.264's fixed tables (ITU-T H.264's), from openh264
(Cisco's, BSD 2-clause), whose text this reads (nothing is compiled or run).

    python3 tools/media/h264_tables.py DIR AVC > libs/media/medialib/h264tables.phi
        # DIR has common_tables.cpp (codec/common/src), wels_common_basis.h (codec/decoder/core/inc)
        # and deblocking.cpp (codec/decoder/core/src) from github.com/cisco/openh264; AVC has
        # ih264_cavlc_tables.c (common/) from Android's libavc (android.googlesource.com/platform/
        # external/libavc, Apache 2.0)

The CABAC contexts' (m, n) (those a kind of slice never uses, openh264's CTX_NA, as 0) for slices of each kind (Tables 9-12 to 9-33: 460, as far as 4:2:0
frames and fields need), the range of the less probable symbol by state and quarter of the range
(Table 9-44) and the next states (Table 9-45), the 4x4 and 8x8 zigzag scans, the 8x8 blocks'
significance and last contexts by position (Table 9-43), the normAdjust numbers for 4x4 and 8x8
(8-315 to 8-318), the chroma QP by QP (Table 8-15), the deblocking filter's alpha, beta and tc0
(Tables 8-16, 8-17) and the default scaling lists (Table 7-3, 7-4). Each is checked for its size
and a few values the standard gives.

CAVLC's (9.2): coeff_token's codes by table (nC 0-1, 2-3, 4-7, and chroma DC's), TotalCoeff and
TrailingOnes (Table 9-5), total_zeros's (Tables 9-7, 9-8, 9-9) and run_before's (Table 9-10), as
lengths and codes, and coded_block_pattern by codeNum (Table 9-4). libavc's are an encoder's tables
(the code for each value), with no codes for a block without coefficients: those (one each, from
Table 9-5) are added, and each table is checked to be a prefix code that its lengths all but fill
(the standard leaves a few codes unused).
"""
import re, sys, os
D = sys.argv[1]
def text(name):
    s = open(os.path.join(D, name)).read()
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
    return re.sub(r'//[^\n]*', '', s)
common = text('common_tables.cpp').replace('CTX_NA', '0')   # (contexts a kind of slice never uses)
basis = text('wels_common_basis.h'); deblock = text('deblocking.cpp')
avc = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', open(os.path.join(sys.argv[2], 'ih264_cavlc_tables.c')).read(), flags=re.S))

def array(src, name):
    m = re.search(re.escape(name) + r'\s*(?:\[[^\]]*\]\s*)+(?:,\s*\d+\s*\))?\s*=\s*\{(.*?)\};', src, re.S)
    assert m, name
    return [int(x) for x in re.findall(r'-?\d+', m.group(1))]

mn = array(common, 'g_kiCabacGlobalContextIdx')
assert len(mn) == 460 * 4 * 2, len(mn)
# (spot checks from Table 9-12 and 9-24: ctxIdx 0 is (20, -15) everywhere; 459 by cabac_init_idc 2 is (20, 64))
assert mn[0:8] == [20, -15] * 4 and mn[459 * 8 + 6: 459 * 8 + 8] == [20, 64], mn[459 * 8:]
lps = array(common, 'g_kuiCabacRangeLps'); assert len(lps) == 256 and lps[0:4] == [128, 176, 208, 240] and lps[252:] == [2, 2, 2, 2]
trans = array(common, 'g_kuiStateTransTable'); assert len(trans) == 128 and trans[124:128] == [38, 62, 63, 63]
zz4 = array(basis, 'g_kuiZigzagScan'); assert zz4 == [0, 1, 4, 8, 5, 2, 3, 6, 9, 12, 13, 10, 7, 11, 14, 15], zz4
zz8 = array(basis, 'g_kuiZigzagScan8x8'); assert len(zz8) == 64 and sorted(zz8) == list(range(64)) and zz8[:6] == [0, 1, 8, 16, 9, 2]
sig8 = array(basis, 'g_kuiIdx2CtxSignificantCoeffFlag8x8'); assert len(sig8) == 64 and max(sig8) == 14
last8 = array(basis, 'g_kuiIdx2CtxLastSignificantCoeffFlag8x8'); assert len(last8) == 64 and last8[-1] == 8
v8 = array(common, 'g_kuiMatrixV'); assert len(v8) == 6 * 64 and v8[:3] == [20, 19, 25] and v8[5 * 64 + 18] == 58
dq = array(common, 'g_kuiDequantCoeff'); assert len(dq) == 52 * 8
cqp = array(common, 'g_kuiChromaQpTable'); assert len(cqp) == 52 and cqp[30] == 29 and cqp[51] == 39
alpha = array(deblock, 'g_kuiAlphaTable'); beta = array(deblock, 'g_kiBetaTable'); tc0 = array(deblock, 'g_kiTc0Table')
assert len(alpha) == 76 and len(beta) == 76 and len(tc0) == 76 * 4
# (openh264's tables start 12 entries early: indexA 16 is the first alpha of 4, 51 the last of 255)
alpha = alpha[12:64]; beta = beta[12:64]; tc0 = [tc0[(12 + i) * 4 + k] for i in range(52) for k in (1, 2, 3)]
assert alpha[16] == 4 and alpha[15] == 0 and alpha[51] == 255 and beta[16] == 2 and beta[51] == 18 and tc0[17 * 3:17 * 3 + 3] == [0, 0, 1] and tc0[51 * 3:] == [13, 17, 25]
d4 = array(common, 'g_kuiDequantScaling4x4Default'); d8 = array(common, 'g_kuiDequantScaling8x8Default')
assert len(d4) == 32 and len(d8) == 128 and d4[:4] == [6, 13, 20, 28] and d8[64:66] == [9, 13]
# normAdjust4x4 by qP % 6: v0 where both coordinates are even, v1 where both are odd, v2 otherwise
v4 = []
for m in range(6):
    a, b, c = dq[m * 8 + 0], dq[m * 8 + 1], dq[m * 8 + 5]
    for i in range(16):
        x, y = i & 3, i >> 2
        v4.append(a if x % 2 == 0 and y % 2 == 0 else c if x % 2 and y % 2 else b)
assert v4[:4] == [10, 13, 10, 13] and v4[5] == 16 and v4[5 * 16 + 5] == 29

# ---- CAVLC ----
def carray(name):
    m = re.search(name + r'\s*(?:\[[^\]]*\]\s*)+=\s*\{(.*?)\};', avc, re.S)
    assert m, name
    return [int(x) for x in re.findall(r'\d+', m.group(1))]
cc = carray('gu1_code_coeff_token_table'); cs = carray('gu1_size_coeff_token_table')
ccc = carray('gu1_code_coeff_token_table_chroma'); ccs = carray('gu1_size_coeff_token_table_chroma')
assert len(cc) == 192 and len(cs) == 192 and len(ccc) == 16 and len(ccs) == 16
# coeff_token by table, TotalCoeff (0 to 16) and TrailingOnes (0 to 3): length (0: no such) and code
ct_len = [0] * (4 * 17 * 4); ct_code = [0] * (4 * 17 * 4)
for t in range(3):
    for t1 in range(4):
        for tc in range(1, 17):
            k = (t * 4 + t1) * 16 + tc - 1
            if cs[k]:
                ct_len[(t * 17 + tc) * 4 + t1] = cs[k]; ct_code[(t * 17 + tc) * 4 + t1] = cc[k]
for t1 in range(4):
    for tc in range(1, 5):
        k = t1 * 4 + tc - 1
        if ccs[k]:
            ct_len[(3 * 17 + tc) * 4 + t1] = ccs[k]; ct_code[(3 * 17 + tc) * 4 + t1] = ccc[k]
# (TotalCoeff 0: "1", "11", "1111" and chroma DC's "01", Table 9-5)
for t, (ln, code) in enumerate([(1, 1), (2, 3), (4, 15), (2, 1)]):
    ct_len[(t * 17) * 4] = ln; ct_code[(t * 17) * 4] = code
def check_prefix(codes, name, full=True):
    codes = [(l, c) for l, c in codes if l]
    for i, (l, c) in enumerate(codes):
        for j, (l2, c2) in enumerate(codes):
            if i != j and l2 >= l and (c2 >> (l2 - l)) == c:
                raise SystemExit('%s: %s is a prefix of %s' % (name, (l, c), (l2, c2)))
    kraft = sum(2.0 ** -l for l, c in codes)
    assert kraft <= 1.0 + 1e-12, (name, kraft)
    return kraft
for t in range(4):
    k = check_prefix([(ct_len[(t * 17 + tc) * 4 + t1], ct_code[(t * 17 + tc) * 4 + t1]) for tc in range(17) for t1 in range(4)], 'coeff_token %d' % t)
    # (Table 9-5 leaves a few codes unused: tables 0 and 1 aren't full, chroma DC's and 2 are)
    assert k > 0.99, (t, k)
zs = carray('gu1_size_zero_table'); zc = carray('gu1_code_zero_table'); zi = carray('gu1_index_zero_table')
zcs = carray('gu1_size_zero_table_chroma'); zcc = carray('gu1_code_zero_table_chroma')
tz_len = [0] * (16 * 16); tz_code = [0] * (16 * 16)
for tc in range(1, 16):
    base = zi[tc - 1]
    for tz in range(17 - tc):
        tz_len[tc * 16 + tz] = zs[base + tz]; tz_code[tc * 16 + tz] = zc[base + tz]
    assert check_prefix([(tz_len[tc * 16 + z], tz_code[tc * 16 + z]) for z in range(16)], 'total_zeros %d' % tc) > 0.99
tzc_len = [0] * (4 * 4); tzc_code = [0] * (4 * 4)
at = 0
for tc in range(1, 4):
    for tz in range(5 - tc):
        tzc_len[tc * 4 + tz] = zcs[at]; tzc_code[tc * 4 + tz] = zcc[at]; at += 1
    assert check_prefix([(tzc_len[tc * 4 + z], tzc_code[tc * 4 + z]) for z in range(4)], 'chroma total_zeros %d' % tc) > 0.99
rs = carray('gu1_size_run_table'); rc = carray('gu1_code_run_table'); ri = carray('gu1_index_run_table')
rb_len = [0] * (7 * 16); rb_code = [0] * (7 * 16)
for zl in range(1, 8):
    base = ri[zl - 1]; n = (zl + 1) if zl < 7 else 15
    for r in range(n):
        rb_len[(zl - 1) * 16 + r] = rs[base + r]; rb_code[(zl - 1) * 16 + r] = rc[base + r]
    kraft = check_prefix([(rb_len[(zl - 1) * 16 + r], rb_code[(zl - 1) * 16 + r]) for r in range(16)], 'run_before %d' % zl)
    assert kraft > 0.99, (zl, kraft)
cbpmap = carray('gu1_cbp_map_tables'); assert len(cbpmap) == 96
cbp_intra = [0] * 48; cbp_inter = [0] * 48
for cbp in range(48):
    cbp_intra[cbpmap[cbp * 2]] = cbp; cbp_inter[cbpmap[cbp * 2 + 1]] = cbp
assert sorted(cbp_intra) == list(range(48)) and cbp_intra[0] == 47 and cbp_inter[0] == 0 and cbp_inter[1] == 16

def rows(vals, per):
    return '\n'.join('\t\t' + ' '.join(str(v) for v in vals[i:i + per]) for i in range(0, len(vals), per))
def table(kind, name, vals, per, note):
    return '\t# %s\n\t%s %s:\n%s;\n' % (note, kind, name, rows(vals, per))

out = ['''# H.264's fixed tables (ITU-T H.264), made by tools/media/h264_tables.py from openh264's text
# (github.com/cisco/openh264, BSD 2-clause; see THIRD_PARTY.md). Don't change them by hand.

phi.MdH264Tables:Library
{
''']
out.append(table('int', 'cabac_mn', mn, 8, "CABAC contexts' m and n (Tables 9-12 to 9-33), by ctxIdx: I slices', then cabac_init_idc 0, 1, 2"))
out.append(table('u8', 'range_lps', lps, 16, "rangeTabLPS by pStateIdx and (codIRange >> 6) & 3 (Table 9-44)"))
out.append(table('u8', 'trans', trans, 16, "the next pStateIdx after a less and a more probable symbol, by pStateIdx (Table 9-45)"))
out.append(table('u8', 'zigzag4', zz4, 16, "the 4x4 frame zigzag scan: the raster position (4 y + x) of each coefficient"))
out.append(table('u8', 'zigzag8', zz8, 16, "the 8x8 frame zigzag scan (8 y + x)"))
out.append(table('u8', 'sig8', sig8, 16, "an 8x8 block's significant_coeff_flag context by position in the scan, frames (Table 9-43)"))
out.append(table('u8', 'last8', last8, 16, "and its last_significant_coeff_flag context"))
out.append(table('u8', 'norm4', v4, 16, "normAdjust4x4 by qP % 6 and raster position (8-315)"))
out.append(table('u8', 'norm8', v8, 16, "normAdjust8x8 by qP % 6 and raster position (8-317, 8-318)"))
out.append(table('u8', 'chroma_qp', cqp, 16, "QPc by qPI (Table 8-15)"))
out.append(table('u8', 'alpha', alpha, 13, "the deblocking filter's alpha' by indexA (Table 8-16)"))
out.append(table('u8', 'beta', beta, 13, "and beta' by indexB"))
out.append(table('u8', 'tc0', tc0, 12, "tc0' by indexA and bS 1, 2, 3 (Table 8-17)"))
out.append(table('u8', 'default4', d4, 16, "the default 4x4 scaling lists, intra then inter, by raster position (Table 7-3)"))
out.append(table('u8', 'default8', d8, 16, "the default 8x8 scaling lists, intra then inter, by raster position (Table 7-4)"))
out.append(table('u8', 'ct_len', ct_len, 16, "CAVLC coeff_token: lengths by table (nC 0-1, 2-3, 4-7, chroma DC), TotalCoeff and TrailingOnes (Table 9-5)"))
out.append(table('u16', 'ct_code', ct_code, 16, "and codes"))
out.append(table('u8', 'tz_len', tz_len, 16, "total_zeros by TotalCoeff and total_zeros, 4x4 blocks (Tables 9-7, 9-8): lengths"))
out.append(table('u8', 'tz_code', tz_code, 16, "and codes"))
out.append(table('u8', 'tzc_len', tzc_len, 16, "chroma DC's (4:2:0, Table 9-9 a)"))
out.append(table('u8', 'tzc_code', tzc_code, 16, "and codes"))
out.append(table('u8', 'rb_len', rb_len, 16, "run_before by zerosLeft (1 to 6, then more) and run_before (Table 9-10)"))
out.append(table('u8', 'rb_code', rb_code, 16, "and codes"))
out.append(table('u8', 'cbp_intra', cbp_intra, 16, "coded_block_pattern by codeNum, Intra_4x4 and Intra_8x8 (Table 9-4)"))
out.append(table('u8', 'cbp_inter', cbp_inter, 16, "and Inter"))
out.append('}\n')
sys.stdout.write('\n'.join(out))
