#!/usr/bin/env python3
# Generates libs/web/css/tables.phi: CSS property ids, keyword ids and the data the runtime table is
# built from. The property table is data, parsed once at start: one line per property, with its
# grammar written in (nearly) CSS's value definition syntax, so the only PHI code a property costs
# is a constant.
#
#   python tools/web/css_gen.py
#
# Grammar notation: a b (sequence), a | b, a || b, a && b, [ ], ? * + # {m,n}, name( ... ), and
# <type>s. A <type> that isn't one of TYPES is a macro below.

import re, os, sys

# ---- terminal types the value parser knows (css/values.phi, CssVp.ParseType)
TYPES = '''length length0 lp lp0 pct pct0 number number0 num01 int int0 int1 numpct numpct0 color url str
ident custom dashed angle angle0 time time0 flex resolution position ratio display family fw areas
linenames urange gridident'''.split()

MACROS = {
 'lw': 'thin | medium | thick | <length0>',
 'bstyle': 'none | hidden | dotted | dashed | solid | double | groove | ridge | inset | outset',
 'size': 'auto | <lp0> | min-content | max-content | fit-content | fit-content( <lp0> ) | stretch | -webkit-fill-available | -moz-available',
 'maxsize': 'none | <lp0> | min-content | max-content | fit-content | fit-content( <lp0> ) | stretch | -webkit-fill-available | -moz-available',
 'shadow': 'inset? && <length>{2,4} && <color>?',
 'tshadow': '<color>? && <length>{2,3}',
 'image': '<url> | <gradient> | image-set( <imgset># ) | -webkit-image-set( <imgset># ) | cross-fade( [ <image> && <pct>? ]# )',
 'imgset': '[ <image> | <str> ] && <resolution>? && [ type( <str> ) ]?',
 'gradient': 'linear-gradient( <lingrad> ) | repeating-linear-gradient( <lingrad> ) | radial-gradient( <radgrad> ) | repeating-radial-gradient( <radgrad> ) | conic-gradient( <congrad> ) | repeating-conic-gradient( <congrad> ) | -webkit-linear-gradient( <lingrad> )',
 'lingrad': '[ [ <angle0> | to [ [ left | right ] || [ top | bottom ] ] ] , ]? <cstop>#',
 'radgrad': '[ [ [ circle | ellipse ] || [ closest-side | closest-corner | farthest-side | farthest-corner | <lp0>{1,2} ] ]? [ at <position> ]? , ]? <cstop>#',
 'congrad': '[ [ from <angle0> ]? [ at <position> ]? , ]? <astop>#',
 'cstop': '[ <color> && <lp>{0,2} ] | <lp>',
 'astop': '[ <color> && [ <angle0> | <pct> ]{0,2} ] | <angle0> | <pct>',
 'bgimage': 'none | <image>',
 'bgsize': '[ <lp0> | auto ]{1,2} | cover | contain',
 'bgrepeat': 'repeat-x | repeat-y | [ repeat | space | round | no-repeat ]{1,2}',
 'box': 'border-box | padding-box | content-box',
 'bgclip': 'border-box | padding-box | content-box | text',
 'blend': 'normal | multiply | screen | overlay | darken | lighten | color-dodge | color-burn | hard-light | soft-light | difference | exclusion | hue | saturation | color | luminosity',
 'tfn': 'matrix( <number> , <number> , <number> , <number> , <number> , <number> ) | '
        'matrix3d( <number># ) | translate( <lp> [ , <lp> ]? ) | translateX( <lp> ) | translateY( <lp> ) | '
        'translateZ( <length> ) | translate3d( <lp> , <lp> , <length> ) | scale( <numpct> [ , <numpct> ]? ) | '
        'scaleX( <numpct> ) | scaleY( <numpct> ) | scaleZ( <numpct> ) | scale3d( <numpct> , <numpct> , <numpct> ) | '
        'rotate( <angle0> ) | rotateX( <angle0> ) | rotateY( <angle0> ) | rotateZ( <angle0> ) | '
        'rotate3d( <number> , <number> , <number> , <angle0> ) | skew( <angle0> [ , <angle0> ]? ) | '
        'skewX( <angle0> ) | skewY( <angle0> ) | perspective( <length0> | none )',
 'ffn': 'blur( <length0>? ) | brightness( <numpct0>? ) | contrast( <numpct0>? ) | grayscale( <numpct0>? ) | '
        'invert( <numpct0>? ) | opacity( <numpct0>? ) | saturate( <numpct0>? ) | sepia( <numpct0>? ) | '
        'hue-rotate( <angle0>? ) | drop-shadow( <tshadow> ) | <url>',
 'easing': 'linear | ease | ease-in | ease-out | ease-in-out | step-start | step-end | '
           'steps( <int1> [ , [ jump-start | jump-end | jump-none | jump-both | start | end ] ]? ) | '
           'cubic-bezier( <number> , <number> , <number> , <number> ) | linear( [ <number> && <pct>{0,2} ]# )',
 'cstyle': 'disc | circle | square | decimal | decimal-leading-zero | lower-roman | upper-roman | lower-greek | '
           'lower-latin | upper-latin | lower-alpha | upper-alpha | armenian | georgian | hebrew | hiragana | '
           'katakana | cjk-decimal | disclosure-open | disclosure-closed | <custom>',
 'breadth': '<lp0> | <flex> | min-content | max-content | auto',
 'inflex': '<lp0> | min-content | max-content | auto',
 'tracksize': '<breadth> | minmax( <inflex> , <breadth> ) | fit-content( <lp0> )',
 'trackrep': 'repeat( [ <int1> | auto-fill | auto-fit ] , [ <linenames>? <tracksize> ]+ <linenames>? )',
 'tracklist': 'none | subgrid <linenames>* | masonry | [ <linenames>? [ <tracksize> | <trackrep> ] ]+ <linenames>?',
 'gridline': 'auto | [ span && [ <int1> || <gridident> ] ] | [ <int> && <gridident>? ] | <gridident>',
 'contentitem': '<str> | <image> | attr( <ident> [ , <str> ]? ) | counter( <custom> [ , <cstyle> ]? ) | '
                'counters( <custom> , <str> [ , <cstyle> ]? ) | open-quote | close-quote | no-open-quote | no-close-quote',
 'bsize': '<lp0> | <number0> | auto',
 'tdline': 'none | [ underline || overline || line-through || blink ]',
 'tdstyle': 'solid | double | dotted | dashed | wavy',
 'tdthick': 'auto | from-font | <lp>',
 'absolute': 'xx-small | x-small | small | medium | large | x-large | xx-large | xxx-large',
 'clipbox': 'border-box | padding-box | content-box | margin-box | fill-box | stroke-box | view-box',
 'basicshape': 'inset( <lp>{1,4} [ round <lp0>+ [ / <lp0>+ ]? ]? ) | circle( <lp0>? [ at <position> ]? ) | '
               'ellipse( [ <lp0>{2} ]? [ at <position> ]? ) | polygon( [ [ nonzero | evenodd ] , ]? [ <lp> <lp> ]# ) | path( [ [ nonzero | evenodd ] , ]? <str> )',
}

CURSORS = ('auto | default | none | context-menu | help | pointer | progress | wait | cell | crosshair | text | '
           'vertical-text | alias | copy | move | no-drop | not-allowed | grab | grabbing | e-resize | n-resize | '
           'ne-resize | nw-resize | s-resize | se-resize | sw-resize | w-resize | ew-resize | ns-resize | nesw-resize | '
           'nwse-resize | col-resize | row-resize | all-scroll | zoom-in | zoom-out | -webkit-grab | -webkit-grabbing | '
           '-webkit-zoom-in | -webkit-zoom-out')

BLINE = 'margin padding'
# (name, flags, group, initial, grammar). flags: i inherited, f applied first (others depend on it)
P = []
def p(name, group, initial, grammar, flags=''):
    P.append((name, flags, group, initial, grammar))

# ---- the fonts, and what text inherits
p('font-size', 'font', 'medium', '<absolute> | larger | smaller | <lp0> | math', 'if')
p('font-family', 'font', 'serif', '<family>#', 'if')
p('font-style', 'font', 'normal', 'normal | italic | oblique <angle>?', 'i')
p('font-weight', 'font', 'normal', 'normal | bold | bolder | lighter | <fw>', 'if')
p('font-stretch', 'font', 'normal', 'normal | ultra-condensed | extra-condensed | condensed | semi-condensed | semi-expanded | expanded | extra-expanded | ultra-expanded | <pct0>', 'i')
p('line-height', 'font', 'normal', 'normal | <number0> | <lp0>', 'i')
p('font-variant-caps', 'font', 'normal', 'normal | small-caps | all-small-caps | petite-caps | all-petite-caps | unicase | titling-caps', 'i')
p('font-variant-ligatures', 'font', 'normal', 'normal | none | [ common-ligatures | no-common-ligatures ] || [ discretionary-ligatures | no-discretionary-ligatures ] || [ historical-ligatures | no-historical-ligatures ] || [ contextual | no-contextual ]', 'i')
p('font-variant-numeric', 'font', 'normal', 'normal | [ lining-nums | oldstyle-nums ] || [ proportional-nums | tabular-nums ] || [ diagonal-fractions | stacked-fractions ] || ordinal || slashed-zero', 'i')
p('font-variant-east-asian', 'font', 'normal', 'normal | [ jis78 | jis83 | jis90 | jis04 | simplified | traditional ] || [ full-width | proportional-width ] || ruby', 'i')
p('font-variant-position', 'font', 'normal', 'normal | sub | super', 'i')
p('font-kerning', 'font', 'auto', 'auto | normal | none', 'i')
p('font-size-adjust', 'font', 'none', 'none | <number0>', 'i')
p('font-feature-settings', 'font', 'normal', 'normal | [ <str> [ <int0> | on | off ]? ]#', 'i')
p('font-variation-settings', 'font', 'normal', 'normal | [ <str> <number> ]#', 'i')
p('font-optical-sizing', 'font', 'auto', 'auto | none', 'i')
p('font-synthesis', 'font', 'weight style small-caps', 'none | weight || style || small-caps', 'i')
p('-webkit-font-smoothing', 'font', 'auto', 'auto | none | antialiased | subpixel-antialiased', 'i')
p('-moz-osx-font-smoothing', 'font', 'auto', 'auto | grayscale', 'i')
p('text-rendering', 'font', 'auto', 'auto | optimizespeed | optimizelegibility | geometricprecision', 'i')

p('color', 'text', 'black', '<color>', 'if')
p('text-align', 'text', 'start', 'start | end | left | right | center | justify | match-parent | -webkit-center | -webkit-left | -webkit-right | -moz-center', 'i')
p('text-align-last', 'text', 'auto', 'auto | start | end | left | right | center | justify | match-parent', 'i')
p('text-indent', 'text', '0px', '<lp> && hanging? && each-line?', 'i')
p('text-transform', 'text', 'none', 'none | capitalize | uppercase | lowercase | full-width | full-size-kana', 'i')
p('white-space', 'text', 'normal', 'normal | pre | nowrap | pre-wrap | pre-line | break-spaces', 'i')
p('white-space-collapse', 'text', 'collapse', 'collapse | preserve | preserve-breaks | preserve-spaces | break-spaces', 'i')
p('text-wrap', 'text', 'wrap', 'wrap | nowrap | balance | stable | pretty', 'i')
p('word-break', 'text', 'normal', 'normal | keep-all | break-all | break-word', 'i')
p('overflow-wrap', 'text', 'normal', 'normal | break-word | anywhere', 'i')
p('hyphens', 'text', 'manual', 'none | manual | auto', 'i')
p('line-break', 'text', 'auto', 'auto | loose | normal | strict | anywhere', 'i')
p('letter-spacing', 'text', 'normal', 'normal | <lp>', 'i')
p('word-spacing', 'text', 'normal', 'normal | <lp>', 'i')
p('tab-size', 'text', '8', '<number0> | <length0>', 'i')
p('direction', 'text', 'ltr', 'ltr | rtl', 'i')
p('writing-mode', 'text', 'horizontal-tb', 'horizontal-tb | vertical-rl | vertical-lr | sideways-rl | sideways-lr | tb | tb-rl | lr | rl', 'i')
p('text-orientation', 'text', 'mixed', 'mixed | upright | sideways', 'i')
p('text-combine-upright', 'text', 'none', 'none | all', 'i')
p('text-justify', 'text', 'auto', 'auto | none | inter-word | inter-character | distribute', 'i')
p('text-shadow', 'text', 'none', 'none | <tshadow>#', 'i')
p('text-underline-position', 'text', 'auto', 'auto | from-font | [ under || [ left | right ] ]', 'i')
p('text-underline-offset', 'text', 'auto', 'auto | <lp>', 'i')
p('text-decoration-skip-ink', 'text', 'auto', 'auto | none | all', 'i')
p('text-emphasis-style', 'text', 'none', 'none | <str> | [ filled | open ] || [ dot | circle | double-circle | triangle | sesame ]', 'i')
p('text-emphasis-color', 'text', 'currentcolor', '<color>', 'i')
p('text-emphasis-position', 'text', 'over right', '[ over | under ] && [ right | left ]?', 'i')
p('text-size-adjust', 'text', 'auto', 'auto | none | <pct0>', 'i')
p('-webkit-text-fill-color', 'text', 'currentcolor', '<color>', 'i')
p('-webkit-text-stroke-width', 'text', '0px', '<lw>', 'i')
p('-webkit-text-stroke-color', 'text', 'currentcolor', '<color>', 'i')
p('-webkit-tap-highlight-color', 'text', 'transparent', '<color>', 'i')
p('caret-color', 'text', 'auto', 'auto | <color>', 'i')
p('accent-color', 'text', 'auto', 'auto | <color>', 'i')
p('color-scheme', 'text', 'normal', 'normal | [ light | dark | <custom> ]+ && only?', 'i')
p('print-color-adjust', 'text', 'economy', 'economy | exact', 'i')
p('-webkit-print-color-adjust', 'text', 'economy', 'economy | exact', 'i')
p('quotes', 'text', 'auto', 'none | auto | [ <str> <str> ]+', 'i')
p('hanging-punctuation', 'text', 'none', 'none | first || [ force-end | allow-end ] || last', 'i')
p('ruby-position', 'text', 'over', 'over | under | alternate | inter-character', 'i')

p('visibility', 'inh', 'visible', 'visible | hidden | collapse', 'i')
p('cursor', 'inh', 'auto', '[ <url> [ <number> <number> ]? , ]* [ ' + CURSORS + ' ]', 'i')
p('list-style-type', 'inh', 'disc', 'none | <str> | <cstyle>', 'i')
p('list-style-position', 'inh', 'outside', 'inside | outside', 'i')
p('list-style-image', 'inh', 'none', 'none | <image>', 'i')
p('border-collapse', 'inh', 'separate', 'collapse | separate', 'i')
p('border-spacing', 'inh', '0px', '<length0>{1,2}', 'i')
p('caption-side', 'inh', 'top', 'top | bottom | block-start | block-end', 'i')
p('empty-cells', 'inh', 'show', 'show | hide', 'i')
p('pointer-events', 'inh', 'auto', 'auto | none | visiblepainted | visiblefill | visiblestroke | visible | painted | fill | stroke | all', 'i')
p('orphans', 'inh', '2', '<int1>', 'i')
p('widows', 'inh', '2', '<int1>', 'i')
p('image-rendering', 'inh', 'auto', 'auto | smooth | high-quality | crisp-edges | pixelated | optimizespeed | optimizequality | -webkit-optimize-contrast', 'i')
p('image-orientation', 'inh', 'from-image', 'from-image | none', 'i')
p('scrollbar-color', 'inh', 'auto', 'auto | <color> <color>', 'i')
p('dominant-baseline', 'inh', 'auto', 'auto | text-bottom | alphabetic | ideographic | middle | central | mathematical | hanging | text-top', 'i')
p('text-anchor', 'inh', 'start', 'start | middle | end', 'i')
p('fill', 'inh', 'black', 'none | context-fill | context-stroke | <color> | <url> [ none | <color> ]?', 'i')
p('fill-opacity', 'inh', '1', '<numpct>', 'i')
p('fill-rule', 'inh', 'nonzero', 'nonzero | evenodd', 'i')
p('stroke', 'inh', 'none', 'none | context-fill | context-stroke | <color> | <url> [ none | <color> ]?', 'i')
p('stroke-width', 'inh', '1px', '<lp0> | <number0>', 'i')
p('stroke-opacity', 'inh', '1', '<numpct>', 'i')
p('stroke-linecap', 'inh', 'butt', 'butt | round | square', 'i')
p('stroke-linejoin', 'inh', 'miter', 'miter | miter-clip | round | bevel | arcs', 'i')
p('stroke-miterlimit', 'inh', '4', '<number0>', 'i')
p('stroke-dasharray', 'inh', 'none', 'none | [ <lp0> | <number0> ]+#', 'i')
p('stroke-dashoffset', 'inh', '0px', '<lp> | <number>', 'i')
p('clip-rule', 'inh', 'nonzero', 'nonzero | evenodd', 'i')
p('shape-rendering', 'inh', 'auto', 'auto | optimizespeed | crispedges | geometricprecision', 'i')
p('paint-order', 'inh', 'normal', 'normal | fill || stroke || markers', 'i')

# ---- the box
p('display', 'box', 'inline', '<display>')
p('position', 'box', 'static', 'static | relative | absolute | fixed | sticky | -webkit-sticky')
p('float', 'box', 'none', 'none | left | right | inline-start | inline-end')
p('clear', 'box', 'none', 'none | left | right | both | inline-start | inline-end')
p('overflow-x', 'box', 'visible', 'visible | hidden | clip | scroll | auto | overlay')
p('overflow-y', 'box', 'visible', 'visible | hidden | clip | scroll | auto | overlay')
p('box-sizing', 'box', 'content-box', 'content-box | border-box')
p('z-index', 'box', 'auto', 'auto | <int>')
p('vertical-align', 'box', 'baseline', 'baseline | sub | super | text-top | text-bottom | middle | top | bottom | <lp>')
p('unicode-bidi', 'box', 'normal', 'normal | embed | isolate | bidi-override | isolate-override | plaintext | -webkit-isolate | -moz-isolate')
p('content', 'box', 'normal', 'normal | none | <contentitem>+ [ / [ <str> | attr( <ident> ) ]+ ]?')
p('table-layout', 'box', 'auto', 'auto | fixed')
p('object-fit', 'box', 'fill', 'fill | contain | cover | none | scale-down')
p('object-position', 'box', '50% 50%', '<position>')
p('text-overflow', 'box', 'clip', '[ clip | ellipsis | <str> ]{1,2}')
p('resize', 'box', 'none', 'none | both | horizontal | vertical | block | inline')
p('appearance', 'box', 'auto', 'none | auto | textfield | menulist-button | button | checkbox | radio | searchfield | textarea | listbox | menulist | meter | progress-bar | push-button | slider-horizontal | square-button | caret')
p('user-select', 'box', 'auto', 'auto | none | text | all | contain')
p('clip', 'box', 'auto', 'auto | rect( [ <length> | auto ] ,? [ <length> | auto ] ,? [ <length> | auto ] ,? [ <length> | auto ] )')
p('zoom', 'box', 'normal', 'normal | reset | <numpct0>')

p('top', 'pos', 'auto', 'auto | <lp>')
p('right', 'pos', 'auto', 'auto | <lp>')
p('bottom', 'pos', 'auto', 'auto | <lp>')
p('left', 'pos', 'auto', 'auto | <lp>')

p('width', 'size', 'auto', '<size>')
p('height', 'size', 'auto', '<size>')
p('min-width', 'size', 'auto', '<size>')
p('min-height', 'size', 'auto', '<size>')
p('max-width', 'size', 'none', '<maxsize>')
p('max-height', 'size', 'none', '<maxsize>')
p('aspect-ratio', 'size', 'auto', 'auto || <ratio>')

p('margin-top', 'margin', '0px', 'auto | <lp>')
p('margin-right', 'margin', '0px', 'auto | <lp>')
p('margin-bottom', 'margin', '0px', 'auto | <lp>')
p('margin-left', 'margin', '0px', 'auto | <lp>')
p('padding-top', 'padding', '0px', '<lp0>')
p('padding-right', 'padding', '0px', '<lp0>')
p('padding-bottom', 'padding', '0px', '<lp0>')
p('padding-left', 'padding', '0px', '<lp0>')

for s in 'top right bottom left'.split():
    p('border-%s-width' % s, 'border', 'medium', '<lw>')
for s in 'top right bottom left'.split():
    p('border-%s-style' % s, 'border', 'none', '<bstyle>')
for s in 'top right bottom left'.split():
    p('border-%s-color' % s, 'border', 'currentcolor', '<color>')
p('border-top-left-radius', 'radius', '0px', '<lp0>{1,2}')
p('border-top-right-radius', 'radius', '0px', '<lp0>{1,2}')
p('border-bottom-right-radius', 'radius', '0px', '<lp0>{1,2}')
p('border-bottom-left-radius', 'radius', '0px', '<lp0>{1,2}')
p('border-image-source', 'radius', 'none', 'none | <image>')
p('border-image-slice', 'radius', '100%', '<numpct0>{1,4} && fill?')
p('border-image-width', 'radius', '1', '[ <lp0> | <number0> | auto ]{1,4}')
p('border-image-outset', 'radius', '0', '[ <length0> | <number0> ]{1,4}')
p('border-image-repeat', 'radius', 'stretch', '[ stretch | repeat | round | space ]{1,2}')
p('box-decoration-break', 'radius', 'slice', 'slice | clone')

p('outline-width', 'outline', 'medium', '<lw>')
p('outline-style', 'outline', 'none', 'auto | <bstyle>')
p('outline-color', 'outline', 'currentcolor', 'auto | <color> | invert')
p('outline-offset', 'outline', '0px', '<length>')

p('background-color', 'bg', 'transparent', '<color>')
p('background-image', 'bg', 'none', '<bgimage>#')
p('background-repeat', 'bg', 'repeat', '<bgrepeat>#')
p('background-attachment', 'bg', 'scroll', '[ scroll | fixed | local ]#')
p('background-position', 'bg', '0% 0%', '<position>#')
p('background-size', 'bg', 'auto', '<bgsize>#')
p('background-origin', 'bg', 'padding-box', '<box>#')
p('background-clip', 'bg', 'border-box', '<bgclip>#')
p('background-blend-mode', 'bg', 'normal', '<blend>#')

# ---- flex, grid, alignment
ALIGNC = 'normal | stretch | baseline | first baseline | last baseline | [ unsafe | safe ]? [ center | start | end | flex-start | flex-end | self-start | self-end | left | right | space-between | space-around | space-evenly ]'
p('flex-direction', 'flex', 'row', 'row | row-reverse | column | column-reverse')
p('flex-wrap', 'flex', 'nowrap', 'nowrap | wrap | wrap-reverse')
p('flex-grow', 'flex', '0', '<number0>')
p('flex-shrink', 'flex', '1', '<number0>')
p('flex-basis', 'flex', 'auto', 'content | <size>')
p('order', 'flex', '0', '<int>')
p('justify-content', 'flex', 'normal', ALIGNC)
p('justify-items', 'flex', 'legacy', 'legacy left | legacy right | legacy center | left legacy | right legacy | center legacy | legacy | ' + ALIGNC)
p('justify-self', 'flex', 'auto', 'auto | ' + ALIGNC)
p('align-content', 'flex', 'normal', ALIGNC)
p('align-items', 'flex', 'normal', ALIGNC)
p('align-self', 'flex', 'auto', 'auto | ' + ALIGNC)
p('row-gap', 'flex', 'normal', 'normal | <lp0>')
p('column-gap', 'flex', 'normal', 'normal | <lp0>')

p('grid-template-columns', 'grid', 'none', '<tracklist>')
p('grid-template-rows', 'grid', 'none', '<tracklist>')
p('grid-template-areas', 'grid', 'none', '<areas>')
p('grid-auto-columns', 'grid', 'auto', '<tracksize>+')
p('grid-auto-rows', 'grid', 'auto', '<tracksize>+')
p('grid-auto-flow', 'grid', 'row', '[ row | column ] || dense')
p('grid-row-start', 'grid', 'auto', '<gridline>')
p('grid-row-end', 'grid', 'auto', '<gridline>')
p('grid-column-start', 'grid', 'auto', '<gridline>')
p('grid-column-end', 'grid', 'auto', '<gridline>')

# ---- transforms, transitions, animations, effects
p('transform', 'xform', 'none', 'none | <tfn>+')
p('transform-origin', 'xform', '50% 50%', '<position> <length>?')
p('transform-style', 'xform', 'flat', 'flat | preserve-3d')
p('transform-box', 'xform', 'view-box', 'content-box | border-box | fill-box | stroke-box | view-box')
p('perspective', 'xform', 'none', 'none | <length0>')
p('perspective-origin', 'xform', '50% 50%', '<position>')
p('backface-visibility', 'xform', 'visible', 'visible | hidden')
p('translate', 'xform', 'none', 'none | <lp> [ <lp> <length>? ]?')
p('rotate', 'xform', 'none', 'none | <number> <number> <number> <angle0> | <angle0> | [ x | y | z ] <angle0>')
p('scale', 'xform', 'none', 'none | <numpct>{1,3}')

p('transition-property', 'anim', 'all', 'none | <ident>#')
p('transition-duration', 'anim', '0s', '<time0>#')
p('transition-timing-function', 'anim', 'ease', '<easing>#')
p('transition-delay', 'anim', '0s', '<time>#')
p('transition-behavior', 'anim', 'normal', '[ normal | allow-discrete ]#')
p('animation-name', 'anim', 'none', '[ none | <custom> | <str> ]#')
p('animation-duration', 'anim', '0s', '[ auto | <time0> ]#')
p('animation-timing-function', 'anim', 'ease', '<easing>#')
p('animation-delay', 'anim', '0s', '<time>#')
p('animation-iteration-count', 'anim', '1', '[ infinite | <number0> ]#')
p('animation-direction', 'anim', 'normal', '[ normal | reverse | alternate | alternate-reverse ]#')
p('animation-fill-mode', 'anim', 'none', '[ none | forwards | backwards | both ]#')
p('animation-play-state', 'anim', 'running', '[ running | paused ]#')
p('animation-composition', 'anim', 'replace', '[ replace | add | accumulate ]#')
p('animation-timeline', 'anim', 'auto', '[ auto | none | <dashed> | <custom> ]#')

p('opacity', 'fx', '1', '<numpct>')
p('box-shadow', 'fx', 'none', 'none | <shadow>#')
p('filter', 'fx', 'none', 'none | <ffn>+')
p('backdrop-filter', 'fx', 'none', 'none | <ffn>+')
p('-webkit-backdrop-filter', 'fx', 'none', 'none | <ffn>+')
p('mix-blend-mode', 'fx', 'normal', '<blend> | plus-lighter | plus-darker')
p('isolation', 'fx', 'auto', 'auto | isolate')
p('clip-path', 'fx', 'none', 'none | <url> | <basicshape> || <clipbox>')
p('mask-image', 'fx', 'none', '<bgimage>#')
p('mask-mode', 'fx', 'match-source', '[ alpha | luminance | match-source ]#')
p('mask-repeat', 'fx', 'repeat', '<bgrepeat>#')
p('mask-position', 'fx', '0% 0%', '<position>#')
p('mask-clip', 'fx', 'border-box', '[ <clipbox> | no-clip ]#')
p('mask-origin', 'fx', 'border-box', '<clipbox>#')
p('mask-size', 'fx', 'auto', '<bgsize>#')
p('mask-composite', 'fx', 'add', '[ add | subtract | intersect | exclude ]#')
p('shape-outside', 'fx', 'none', 'none | <image> | <basicshape> || [ margin-box | border-box | padding-box | content-box ]')
p('shape-margin', 'fx', '0px', '<lp0>')
p('shape-image-threshold', 'fx', '0', '<number>')
p('will-change', 'fx', 'auto', 'auto | <ident>#')
p('contain', 'fx', 'none', 'none | strict | content | size || inline-size || layout || style || paint')
p('content-visibility', 'fx', 'visible', 'visible | hidden | auto')
p('contain-intrinsic-width', 'fx', 'none', 'none | auto? <length0>')
p('contain-intrinsic-height', 'fx', 'none', 'none | auto? <length0>')
p('container-type', 'fx', 'normal', 'normal | size | inline-size')
p('container-name', 'fx', 'none', 'none | <custom>+')
p('forced-color-adjust', 'fx', 'auto', 'auto | none | preserve-parent-color')
p('stop-color', 'fx', 'black', '<color>')
p('stop-opacity', 'fx', '1', '<numpct>')
p('flood-color', 'fx', 'black', '<color>')
p('flood-opacity', 'fx', '1', '<numpct>')
p('lighting-color', 'fx', 'white', '<color>')
p('vector-effect', 'fx', 'none', 'none | non-scaling-stroke')

# ---- text decoration, lists of things that don't inherit
p('text-decoration-line', 'misc', 'none', '<tdline>')
p('text-decoration-style', 'misc', 'solid', '<tdstyle>')
p('text-decoration-color', 'misc', 'currentcolor', '<color>')
p('text-decoration-thickness', 'misc', 'auto', '<tdthick>')
p('counter-reset', 'misc', 'none', 'none | [ <custom> <int>? ]+')
p('counter-increment', 'misc', 'none', 'none | [ <custom> <int>? ]+')
p('counter-set', 'misc', 'none', 'none | [ <custom> <int>? ]+')
p('column-count', 'misc', 'auto', 'auto | <int1>')
p('column-width', 'misc', 'auto', 'auto | <length0>')
p('column-fill', 'misc', 'balance', 'auto | balance | balance-all')
p('column-span', 'misc', 'none', 'none | all')
p('column-rule-width', 'misc', 'medium', '<lw>')
p('column-rule-style', 'misc', 'none', '<bstyle>')
p('column-rule-color', 'misc', 'currentcolor', '<color>')
p('break-before', 'misc', 'auto', 'auto | avoid | always | all | avoid-page | page | left | right | recto | verso | avoid-column | column | avoid-region | region')
p('break-after', 'misc', 'auto', 'auto | avoid | always | all | avoid-page | page | left | right | recto | verso | avoid-column | column | avoid-region | region')
p('break-inside', 'misc', 'auto', 'auto | avoid | avoid-page | avoid-column | avoid-region')
p('scroll-behavior', 'misc', 'auto', 'auto | smooth')
p('overscroll-behavior-x', 'misc', 'auto', 'auto | contain | none')
p('overscroll-behavior-y', 'misc', 'auto', 'auto | contain | none')
p('overflow-anchor', 'misc', 'auto', 'auto | none')
p('scroll-snap-type', 'misc', 'none', 'none | [ x | y | block | inline | both ] [ mandatory | proximity ]?')
p('scroll-snap-align', 'misc', 'none', '[ none | start | end | center ]{1,2}')
p('scroll-snap-stop', 'misc', 'normal', 'normal | always')
for s in 'top right bottom left'.split():
    p('scroll-margin-%s' % s, 'misc', '0px', '<length>')
for s in 'top right bottom left'.split():
    p('scroll-padding-%s' % s, 'misc', 'auto', 'auto | <lp0>')
p('touch-action', 'misc', 'auto', 'auto | none | manipulation | [ pan-x | pan-left | pan-right ] || [ pan-y | pan-up | pan-down ] || pinch-zoom')
p('scrollbar-width', 'misc', 'auto', 'auto | thin | none')
p('scrollbar-gutter', 'misc', 'auto', 'auto | stable && both-edges?')
p('-webkit-line-clamp', 'misc', 'none', 'none | <int1>')
p('-webkit-box-orient', 'misc', 'horizontal', 'horizontal | vertical | inline-axis | block-axis')
p('-webkit-overflow-scrolling', 'misc', 'auto', 'auto | touch')

# ---- shorthands: name, kind, longhands
SIDES = 'top right bottom left'.split()
S = []
def sh(name, kind, subs): S.append((name, kind, subs))
sh('margin', 'box4', ['margin-' + s for s in SIDES])
sh('padding', 'box4', ['padding-' + s for s in SIDES])
sh('inset', 'box4', SIDES)
sh('border-width', 'box4', ['border-%s-width' % s for s in SIDES])
sh('border-style', 'box4', ['border-%s-style' % s for s in SIDES])
sh('border-color', 'box4', ['border-%s-color' % s for s in SIDES])
sh('scroll-margin', 'box4', ['scroll-margin-' + s for s in SIDES])
sh('scroll-padding', 'box4', ['scroll-padding-' + s for s in SIDES])
for s in SIDES:
    sh('border-' + s, 'any', ['border-%s-%s' % (s, x) for x in ('width', 'style', 'color')])
sh('border', 'border', ['border-%s-%s' % (s, x) for x in ('width', 'style', 'color') for s in SIDES]
   + ['border-image-source', 'border-image-slice', 'border-image-width', 'border-image-outset', 'border-image-repeat'])
sh('border-radius', 'radius', ['border-top-left-radius', 'border-top-right-radius', 'border-bottom-right-radius', 'border-bottom-left-radius'])
sh('border-image', 'custom', ['border-image-source', 'border-image-slice', 'border-image-width', 'border-image-outset', 'border-image-repeat'])
sh('outline', 'any', ['outline-width', 'outline-style', 'outline-color'])
sh('list-style', 'any', ['list-style-type', 'list-style-position', 'list-style-image'])
sh('text-decoration', 'any', ['text-decoration-line', 'text-decoration-style', 'text-decoration-color', 'text-decoration-thickness'])
sh('text-emphasis', 'any', ['text-emphasis-style', 'text-emphasis-color'])
sh('column-rule', 'any', ['column-rule-width', 'column-rule-style', 'column-rule-color'])
sh('columns', 'any', ['column-width', 'column-count'])
sh('flex-flow', 'any', ['flex-direction', 'flex-wrap'])
sh('font-variant', 'any', ['font-variant-ligatures', 'font-variant-caps', 'font-variant-numeric', 'font-variant-east-asian', 'font-variant-position'])
sh('-webkit-text-stroke', 'any', ['-webkit-text-stroke-width', '-webkit-text-stroke-color'])
sh('overflow', 'pair', ['overflow-x', 'overflow-y'])
sh('overscroll-behavior', 'pair', ['overscroll-behavior-x', 'overscroll-behavior-y'])
sh('gap', 'pair', ['row-gap', 'column-gap'])
sh('grid-gap', 'pair', ['row-gap', 'column-gap'])
sh('place-content', 'pair', ['align-content', 'justify-content'])
sh('place-items', 'pair', ['align-items', 'justify-items'])
sh('place-self', 'pair', ['align-self', 'justify-self'])
sh('contain-intrinsic-size', 'pair', ['contain-intrinsic-width', 'contain-intrinsic-height'])
sh('grid-row', 'slash', ['grid-row-start', 'grid-row-end'])
sh('grid-column', 'slash', ['grid-column-start', 'grid-column-end'])
sh('grid-area', 'slash', ['grid-row-start', 'grid-column-start', 'grid-row-end', 'grid-column-end'])
sh('background', 'background', ['background-image', 'background-position', 'background-size', 'background-repeat', 'background-attachment', 'background-origin', 'background-clip', 'background-color'])
sh('mask', 'custom', ['mask-image', 'mask-mode', 'mask-repeat', 'mask-position', 'mask-clip', 'mask-origin', 'mask-size', 'mask-composite'])
sh('font', 'font', ['font-style', 'font-variant-caps', 'font-weight', 'font-stretch', 'font-size', 'line-height', 'font-family',
                    'font-variant-ligatures', 'font-variant-numeric', 'font-variant-east-asian', 'font-variant-position', 'font-kerning', 'font-size-adjust', 'font-feature-settings', 'font-variation-settings', 'font-optical-sizing'])
sh('flex', 'flex', ['flex-grow', 'flex-shrink', 'flex-basis'])
sh('transition', 'layers', ['transition-property', 'transition-duration', 'transition-timing-function', 'transition-delay', 'transition-behavior'])
sh('animation', 'layers', ['animation-name', 'animation-duration', 'animation-timing-function', 'animation-delay', 'animation-iteration-count', 'animation-direction', 'animation-fill-mode', 'animation-play-state'])
sh('grid-template', 'gridtemplate', ['grid-template-rows', 'grid-template-columns', 'grid-template-areas'])
sh('grid', 'grid', ['grid-template-rows', 'grid-template-columns', 'grid-template-areas', 'grid-auto-rows', 'grid-auto-columns', 'grid-auto-flow'])
sh('container', 'custom', ['container-name', 'container-type'])
sh('all', 'all', [])

# other names for a property (logical properties mean their horizontal, left-to-right side)
ALIASES = {
 'word-wrap': 'overflow-wrap', 'grid-row-gap': 'row-gap', 'grid-column-gap': 'column-gap',
 'page-break-before': 'break-before', 'page-break-after': 'break-after', 'page-break-inside': 'break-inside',
 'inline-size': 'width', 'block-size': 'height', 'min-inline-size': 'min-width', 'min-block-size': 'min-height',
 'max-inline-size': 'max-width', 'max-block-size': 'max-height',
 'margin-inline-start': 'margin-left', 'margin-inline-end': 'margin-right', 'margin-block-start': 'margin-top', 'margin-block-end': 'margin-bottom',
 'padding-inline-start': 'padding-left', 'padding-inline-end': 'padding-right', 'padding-block-start': 'padding-top', 'padding-block-end': 'padding-bottom',
 'inset-inline-start': 'left', 'inset-inline-end': 'right', 'inset-block-start': 'top', 'inset-block-end': 'bottom',
 'border-inline-start': 'border-left', 'border-inline-end': 'border-right', 'border-block-start': 'border-top', 'border-block-end': 'border-bottom',
 'border-inline-start-width': 'border-left-width', 'border-inline-end-width': 'border-right-width', 'border-block-start-width': 'border-top-width', 'border-block-end-width': 'border-bottom-width',
 'border-inline-start-style': 'border-left-style', 'border-inline-end-style': 'border-right-style', 'border-block-start-style': 'border-top-style', 'border-block-end-style': 'border-bottom-style',
 'border-inline-start-color': 'border-left-color', 'border-inline-end-color': 'border-right-color', 'border-block-start-color': 'border-top-color', 'border-block-end-color': 'border-bottom-color',
 'border-start-start-radius': 'border-top-left-radius', 'border-start-end-radius': 'border-top-right-radius', 'border-end-start-radius': 'border-bottom-left-radius', 'border-end-end-radius': 'border-bottom-right-radius',
 'scroll-margin-inline-start': 'scroll-margin-left', 'scroll-margin-inline-end': 'scroll-margin-right', 'scroll-margin-block-start': 'scroll-margin-top', 'scroll-margin-block-end': 'scroll-margin-bottom',
 'scroll-padding-inline-start': 'scroll-padding-left', 'scroll-padding-inline-end': 'scroll-padding-right', 'scroll-padding-block-start': 'scroll-padding-top', 'scroll-padding-block-end': 'scroll-padding-bottom',
}
# two sides at once, written like a pair
LOGICAL_PAIRS = {
 'margin-inline': ['margin-left', 'margin-right'], 'margin-block': ['margin-top', 'margin-bottom'],
 'padding-inline': ['padding-left', 'padding-right'], 'padding-block': ['padding-top', 'padding-bottom'],
 'inset-inline': ['left', 'right'], 'inset-block': ['top', 'bottom'],
 'border-inline-width': ['border-left-width', 'border-right-width'], 'border-block-width': ['border-top-width', 'border-bottom-width'],
 'border-inline-style': ['border-left-style', 'border-right-style'], 'border-block-style': ['border-top-style', 'border-bottom-style'],
 'border-inline-color': ['border-left-color', 'border-right-color'], 'border-block-color': ['border-top-color', 'border-bottom-color'],
 'scroll-margin-inline': ['scroll-margin-left', 'scroll-margin-right'], 'scroll-margin-block': ['scroll-margin-top', 'scroll-margin-bottom'],
 'scroll-padding-inline': ['scroll-padding-left', 'scroll-padding-right'], 'scroll-padding-block': ['scroll-padding-top', 'scroll-padding-bottom'],
}
for k, v in LOGICAL_PAIRS.items():
    sh(k, 'pair', v)
sh('border-inline', 'any2', ['border-left', 'border-right'])
sh('border-block', 'any2', ['border-top', 'border-bottom'])

# ---- words the code names that no grammar mentions
UNITS = '''px em rem ex ch vw vh vmin vmax cm mm in pt pc q lh rlh cap ic svw svh lvw lvh dvw dvh vi vb svi svb
lvi lvb dvi dvb svmin svmax lvmin lvmax dvmin dvmax
deg rad grad turn s ms dpi dpcm dppx x fr hz khz'''.split()
UNIT_LEN = UNITS.index('deg')    # the lengths; then 4 angles, 2 times, 4 resolutions, fr, 2 frequencies

COLORS = '''aliceblue f0f8ff antiquewhite faebd7 aqua 00ffff aquamarine 7fffd4 azure f0ffff beige f5f5dc bisque ffe4c4
black 000000 blanchedalmond ffebcd blue 0000ff blueviolet 8a2be2 brown a52a2a burlywood deb887 cadetblue 5f9ea0
chartreuse 7fff00 chocolate d2691e coral ff7f50 cornflowerblue 6495ed cornsilk fff8dc crimson dc143c cyan 00ffff
darkblue 00008b darkcyan 008b8b darkgoldenrod b8860b darkgray a9a9a9 darkgreen 006400 darkgrey a9a9a9 darkkhaki bdb76b
darkmagenta 8b008b darkolivegreen 556b2f darkorange ff8c00 darkorchid 9932cc darkred 8b0000 darksalmon e9967a
darkseagreen 8fbc8f darkslateblue 483d8b darkslategray 2f4f4f darkslategrey 2f4f4f darkturquoise 00ced1 darkviolet 9400d3
deeppink ff1493 deepskyblue 00bfff dimgray 696969 dimgrey 696969 dodgerblue 1e90ff firebrick b22222 floralwhite fffaf0
forestgreen 228b22 fuchsia ff00ff gainsboro dcdcdc ghostwhite f8f8ff gold ffd700 goldenrod daa520 gray 808080 green 008000
greenyellow adff2f grey 808080 honeydew f0fff0 hotpink ff69b4 indianred cd5c5c indigo 4b0082 ivory fffff0 khaki f0e68c
lavender e6e6fa lavenderblush fff0f5 lawngreen 7cfc00 lemonchiffon fffacd lightblue add8e6 lightcoral f08080 lightcyan e0ffff
lightgoldenrodyellow fafad2 lightgray d3d3d3 lightgreen 90ee90 lightgrey d3d3d3 lightpink ffb6c1 lightsalmon ffa07a
lightseagreen 20b2aa lightskyblue 87cefa lightslategray 778899 lightslategrey 778899 lightsteelblue b0c4de lightyellow ffffe0
lime 00ff00 limegreen 32cd32 linen faf0e6 magenta ff00ff maroon 800000 mediumaquamarine 66cdaa mediumblue 0000cd
mediumorchid ba55d3 mediumpurple 9370db mediumseagreen 3cb371 mediumslateblue 7b68ee mediumspringgreen 00fa9a
mediumturquoise 48d1cc mediumvioletred c71585 midnightblue 191970 mintcream f5fffa mistyrose ffe4e1 moccasin ffe4b5
navajowhite ffdead navy 000080 oldlace fdf5e6 olive 808000 olivedrab 6b8e23 orange ffa500 orangered ff4500 orchid da70d6
palegoldenrod eee8aa palegreen 98fb98 paleturquoise afeeee palevioletred db7093 papayawhip ffefd5 peachpuff ffdab9
peru cd853f pink ffc0cb plum dda0dd powderblue b0e0e6 purple 800080 rebeccapurple 663399 red ff0000 rosybrown bc8f8f
royalblue 4169e1 saddlebrown 8b4513 salmon fa8072 sandybrown f4a460 seagreen 2e8b57 seashell fff5ee sienna a0522d
silver c0c0c0 skyblue 87ceeb slateblue 6a5acd slategray 708090 slategrey 708090 snow fffafa springgreen 00ff7f
steelblue 4682b4 tan d2b48c teal 008080 thistle d8bfd8 tomato ff6347 turquoise 40e0d0 violet ee82ee wheat f5deb3
white ffffff whitesmoke f5f5f5 yellow ffff00 yellowgreen 9acd32
canvas ffffff canvastext 000000 linktext 0000ee visitedtext 551a8b activetext ff0000 buttonface efefef buttontext 000000
buttonborder 767676 field ffffff fieldtext 000000 highlight 3367d1 highlighttext ffffff selecteditem 3367d1
selecteditemtext ffffff mark ffff00 marktext 000000 graytext 808080 accentcolor 0075ff accentcolortext ffffff
activeborder 767676 activecaption ffffff appworkspace ffffff background ffffff buttonhighlight efefef buttonshadow 767676
captiontext 000000 inactiveborder 767676 inactivecaption ffffff inactivecaptiontext 808080 infobackground ffffff
infotext 000000 menu ffffff menutext 000000 scrollbar ffffff threeddarkshadow 767676 threedface efefef
threedhighlight efefef threedlightshadow efefef threedshadow 767676 window ffffff windowframe 767676 windowtext 000000'''.split()

EXTRA_WORDS = '''inherit initial unset revert revert-layer important var calc min max clamp currentcolor transparent none
rgb rgba hsl hsla hwb lab lch oklab oklch color color-mix srgb srgb-linear display-p3 a98-rgb prophoto-rgb rec2020 xyz xyz-d50 xyz-d65
device-cmyk from in and or not only all screen print speech supports selector layer media import charset namespace font-face
keyframes page font-feature-values counter-style property container url src format local tech unicode-range font-display
ascent-override descent-override line-gap-override size-adjust block swap fallback optional
scroll inline flow-root contents list-item table inline-table table-row table-cell table-row-group table-header-group
table-footer-group table-column table-column-group table-caption flex inline-flex grid inline-grid ruby ruby-base ruby-text
ruby-base-container ruby-text-container inline-block -webkit-box -webkit-inline-box -webkit-flex -webkit-inline-flex -moz-box flow math
span auto normal bold bolder lighter italic oblique larger smaller
serif sans-serif monospace cursive fantasy system-ui
caption icon menu message-box small-caption status-bar
landscape portrait light dark no-preference reduce more less custom
fine coarse hover active focus focus-visible focus-within visited target link any-link checked disabled enabled required
optional read-only read-write placeholder-shown default lang dir root first-child last-child only-child nth-child nth-last-child
first-of-type last-of-type only-of-type nth-of-type nth-last-of-type empty is where has scope matches -webkit-any -moz-any
indeterminate valid invalid in-range out-of-range defined fullscreen modal popover-open autofill -webkit-autofill user-valid user-invalid
paused playing past future current target-within local-link blank host
before after first-line first-letter marker selection placeholder backdrop file-selector-button
-webkit-input-placeholder -moz-placeholder -ms-input-placeholder
ltr rtl n of even odd s i
width height min-width max-width min-height max-height aspect-ratio min-aspect-ratio max-aspect-ratio orientation
device-width device-height min-device-width max-device-width min-device-height max-device-height device-aspect-ratio
min-device-aspect-ratio max-device-aspect-ratio resolution min-resolution max-resolution scan progressive interlace
update slow fast overflow-block overflow-inline paged optional-paged color-index min-color max-color min-color-index max-color-index
monochrome min-monochrome max-monochrome color-gamut p3 inverted-colors inverted pointer any-pointer any-hover
prefers-color-scheme prefers-reduced-motion prefers-contrast prefers-reduced-transparency prefers-reduced-data forced-colors
display-mode browser standalone minimal-ui scripting enabled initial-only environment-blending video-color-gamut
active-only high low -webkit-min-device-pixel-ratio -webkit-max-device-pixel-ratio -webkit-device-pixel-ratio min--moz-device-pixel-ratio
sub super baseline top right bottom left center start end
font-family font-weight font-stretch font-style light-dark -webkit-keyframes auto-flow dense row column to attr
'''.split()

def ident(word):
    return re.sub(r'[^A-Za-z0-9]', '_', word).upper()

def grammar_words(g):
    # the words in a grammar: no <types>, and functions without the (
    g = re.sub(r'<[^>]*>', ' ', g)
    g = re.sub(r'\{[^}]*\}', ' ', g)
    return re.findall(r'-?[a-zA-Z][-a-zA-Z0-9]*', g)

def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'libs', 'web', 'css')
    words = []
    seen = set()
    def add(w):
        w = w.lower()
        if w not in seen:
            seen.add(w)
            words.append(w)
    for n, f, g, i, gr in P:
        for w in grammar_words(gr): add(w)
        for w in grammar_words(i): add(w)
    for m in MACROS.values():
        for w in grammar_words(m): add(w)
    for w in UNITS: add(w)
    for w in COLORS[0::2]: add(w)
    for w in EXTRA_WORDS: add(w)
    # names of properties too: transition-property keeps them, and @supports asks about them
    assert len(words) < 4095, len(words)

    groups = []
    for n, f, g, i, gr in P:
        if g not in groups: groups.append(g)
    slots = {g: 0 for g in groups}
    inherited = {}
    prop_lines = []
    for n, f, g, i, gr in P:
        assert slots[g] < 250
        inh = 'i' in f
        assert inherited.setdefault(g, inh) == inh, (n, g)
        slots[g] += 1
        prop_lines.append('%s|%s|%d|%s|%s' % (n, f or '-', groups.index(g), i, gr))
    names = [x[0] for x in P] + [x[0] for x in S]
    assert len(set(names)) == len(names), [n for n in names if names.count(n) > 1]
    for n, k, subs in S:
        for x in subs:
            assert x in names, (n, x)
        prop_lines.append('%s|S|%s|%s' % (n, k, ' '.join(subs)))
    for a, t in ALIASES.items():
        assert t in names, (a, t)
        prop_lines.append('%s|A|%s' % (a, t))
    macro_lines = ['%s|%s' % (k, v) for k, v in MACROS.items()]
    for t in re.findall(r'<(\w+)>', ' '.join(x[4] for x in P) + ' ' + ' '.join(MACROS.values())):
        assert t in TYPES or t in MACROS, t

    def literal(lines):
        # a literal per line is easy on the compiler; a line can't hold a quote or a backslash
        for ln in lines:
            assert "'" not in ln and '\\' not in ln, ln
        return (chr(92) + 'n').join(lines)

    def chunks(text, name):
        out = []
        out.append('\t[%s]\n\t\tptr<u8> text: \'%s\';\n\t[end: text]\n\n' % (name, text))
        return ''.join(out)

    o = []
    o.append('# Generated by tools/css_gen.py: edit that, not this.\n\n')
    o.append('phi.CssK:Library\n{\n')
    for idx, w in enumerate(words):
        o.append('\tconst u32 %s: %d;\n' % (ident(w), idx + 1))
    o.append('\tconst u32 COUNT: %d;\n}\n\n' % (len(words) + 1))
    o.append('phi.CssP:Library\n{\n')
    for idx, x in enumerate(P):
        o.append('\tconst u32 %s: %d;\n' % (ident(x[0]), idx))
    for idx, x in enumerate(S):
        o.append('\tconst u32 %s: %d;\n' % (ident(x[0]), idx + len(P)))
    o.append('\tconst u32 LONGHANDS: %d;\n\tconst u32 COUNT: %d;\n\tconst u32 CUSTOM: 0xFFFF;\n' % (len(P), len(P) + len(S)))
    o.append('\tconst u32 GROUPS: %d;\n' % len(groups))
    for i, g in enumerate(groups):
        o.append('\tconst u32 G_%s: %d;\n' % (g.upper(), i))
    o.append('}\n\n')
    for idx, t in enumerate(TYPES):
        pass
    o.append('phi.CssT:Library\n{\n')
    for idx, t in enumerate(TYPES):
        o.append('\tconst u32 %s: %d;\n' % (t.upper(), idx + 1))
    o.append('}\n\n')
    o.append('phi.CssU:Library\n{\n')
    for idx, u in enumerate(UNITS):
        o.append('\tconst u32 %s: %d;\n' % (ident(u), idx + 1))
    o.append('\tconst u32 LAST_LENGTH: %d;\n\tconst u32 LAST_ANGLE: %d;\n\tconst u32 LAST_TIME: %d;\n\tconst u32 LAST_RES: %d;\n\tconst u32 COUNT: %d;\n}\n\n' %
             (UNIT_LEN, UNIT_LEN + 4, UNIT_LEN + 6, UNIT_LEN + 10, len(UNITS) + 1))
    o.append('phi.CssTab:Library\n{\n')
    o.append(chunks(literal(words), 'Words').replace('\n\';', '\';', 1))
    o.append(chunks(' '.join(UNITS) + ' ', 'Units'))
    o.append(chunks(literal(prop_lines), 'Props'))
    o.append(chunks(literal(macro_lines), 'Macros'))
    o.append(chunks(' '.join(TYPES) + ' ', 'Types'))
    o.append(chunks(' '.join(COLORS) + ' ', 'Colors'))
    o.append('}\n')
    path = os.path.join(root, 'tables.phi')
    with open(path, 'w', newline='\n') as f:
        f.write(''.join(o))
    print('%d keywords, %d longhands, %d shorthands, %d groups, %d aliases; %d bytes' %
          (len(words), len(P), len(S), len(groups), len(ALIASES), os.path.getsize(path)))
    print('group sizes', slots)

main()
