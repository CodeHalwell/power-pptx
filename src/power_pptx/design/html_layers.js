root => {
    const base = root.getBoundingClientRect();
    const style = el => {
        const s = getComputedStyle(el);
        return {font:s.fontFamily, size:parseFloat(s.fontSize), weight:s.fontWeight,
            italic:s.fontStyle !== 'normal', color:s.color, align:s.textAlign,
            lineHeight:parseFloat(s.lineHeight) || parseFloat(s.fontSize)*1.2,
            underline:s.textDecorationLine.includes('underline'), opacity:parseFloat(s.opacity),
            padding:[s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft].map(parseFloat),
            border:[s.borderTopWidth,s.borderRightWidth,s.borderBottomWidth,s.borderLeftWidth].map(parseFloat),
            borderColors:[s.borderTopColor,s.borderRightColor,s.borderBottomColor,s.borderLeftColor],
            verticalAlign:s.verticalAlign};
    };
    const bounds = el => { const b=el.getBoundingClientRect();
        return [b.x-base.x,b.y-base.y,b.width,b.height]; };
    const nodes = [...root.querySelectorAll('[data-pptx]')];
    return nodes.map((el,index) => {
        const kind=el.getAttribute('data-pptx');
        const fail = message => {throw new Error(`data-pptx region ${index+1}: ${message}`)};
        if (!['text','chart','table','capture'].includes(kind)) fail('expected text, chart, table, or capture');
        if (el.parentElement.closest('[data-pptx]')) fail('annotations cannot be nested');
        const box=bounds(el), s=getComputedStyle(el), formatting=style(el);
        if (box[2]<=0 || box[3]<=0 || s.display==='none' || s.visibility==='hidden') fail('region is not visible');
        if (box[0]<-1 || box[1]<-1 || box[0]+box[2]>base.width+1 || box[1]+box[3]>base.height+1)
            fail('region extends beyond its slide');
        if (kind!=='capture') {
            for (let a=el; a && a!==root.parentElement; a=a.parentElement) {
                const cs=getComputedStyle(a);
                if (cs.transform!=='none' || cs.perspective!=='none' || cs.filter!=='none')
                    fail('transformed native regions need data-pptx="capture"');
            }
            if (el.scrollWidth>el.clientWidth+1 || el.scrollHeight>el.clientHeight+1)
                fail('native region overflows its box');
            if (s.boxShadow!=='none' || s.clipPath!=='none' || s.mixBlendMode!=='normal' ||
                (s.maskImage || s.webkitMaskImage || 'none')!=='none')
                fail('native region effects require capture');
            if (kind!=='text') {
                if (s.backgroundImage!=='none' || parseFloat(s.borderRadius)>0)
                    fail('native chart/table decorations require an unmarked parent or capture');
                for(let a=el;a && a!==root.parentElement;a=a.parentElement)
                    if(parseFloat(getComputedStyle(a).opacity)!==1)
                        fail('native chart/table opacity requires capture');
            }
        }
        const result={kind, bounds:box, style:formatting, name:el.getAttribute('data-name') || el.id || `HTML ${kind} ${index+1}`,
            text:el.innerText || el.getAttribute('aria-label') || '', order:parseInt(s.zIndex)||0, index};
        if (kind==='text') {
            const checkTextStyle = cs => {
                if (cs.textTransform!=='none') fail('text transforms require capture or authored transformed text');
                if (!['normal','0px'].includes(cs.letterSpacing) || cs.textShadow!=='none' ||
                    cs.backgroundImage!=='none' || cs.backgroundColor!=='rgba(0, 0, 0, 0)' ||
                    ['Top','Right','Bottom','Left'].some(edge=>parseFloat(cs['border'+edge+'Width'])>0))
                    fail('native text decorations/backgrounds require an unmarked parent or capture');
                if (cs.verticalAlign!=='baseline') fail('superscript and subscript require capture');
            };
            checkTextStyle(s);
            if (!['normal','0px'].includes(s.letterSpacing) || s.textShadow!=='none' ||
                s.backgroundImage!=='none' || s.webkitTextFillColor==='rgba(0, 0, 0, 0)' || s.textIndent!=='0px')
                fail('letter spacing, gradient/shadow text, and indentation require capture');
            if (s.writingMode!=='horizontal-tb' || s.direction==='rtl') fail('vertical/RTL text requires capture');
            if (el.querySelector('img,svg,canvas,video')) fail('text regions cannot contain visuals');
            if (el.textContent.length>20000) fail('text region is too large; split it into slides');
            const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
            const runs=[]; let node, firstY=null, line=0, previousY=null;
            while (node=walker.nextNode()) {
                const parent=node.parentElement, cs=getComputedStyle(parent);
                if (['SCRIPT','STYLE'].includes(parent.tagName) || cs.display==='none' || cs.visibility==='hidden') continue;
                const f=style(parent);
                checkTextStyle(cs);
                if (Math.abs(f.size-formatting.size)>.1) fail('mixed font sizes require separate annotated text regions');
                let opacity=1;
                for(let a=parent;a && a!==root.parentElement;a=a.parentElement) opacity*=parseFloat(getComputedStyle(a).opacity);
                f.opacity=opacity;
                const signature=JSON.stringify(f);
                for(let i=0;i<node.length;i++) {
                    const range=document.createRange();range.setStart(node,i);range.setEnd(node,i+1);
                    const b=range.getBoundingClientRect(), char=node.textContent[i];
                    if (!b.height || (/\s/.test(char) && b.width<.01)) continue;
                    if (firstY===null) firstY=b.y;
                    if (previousY!==null && Math.abs(b.y-previousY)>f.size*.6)
                        line+=Math.max(1,Math.round((b.y-previousY)/formatting.lineHeight));
                    previousY=b.y;
                    const last=runs[runs.length-1];
                    if(last && last.line===line && last.signature===signature) last.text+=char;
                    else runs.push({text:char,line,style:f,signature});
                }
            }
            result.runs=runs;
        }
        if (kind==='chart') {
            const spec=el.getAttribute('data-pptx-chart');
            if (!spec) fail('chart requires a data-pptx-chart JSON specification');
            try {result.chart=JSON.parse(spec)} catch {fail('invalid chart JSON')}
        }
        if (kind==='table') {
            if(el.tagName!=='TABLE') fail('table annotation belongs on a table element');
            if(el.querySelector('caption,table')) fail('captions and nested tables require separate regions');
            result.rows=[...el.rows].map(row=>[...row.cells].map(cell=>({text:cell.innerText,
                colspan:cell.colSpan,rowspan:cell.rowSpan,style:style(cell),
                fill:getComputedStyle(cell).backgroundColor,bounds:bounds(cell)})));
            result.rowHeights=[...el.rows].map(row=>row.getBoundingClientRect().height);
        }
        return result;
    });
}
