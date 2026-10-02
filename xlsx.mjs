/* ---------- minimal .xlsx writer (no external library) ---------- */
const XLSX_W=(()=>{
  const enc=new TextEncoder();
  const CRC=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
  const crc32=b=>{let c=0xFFFFFFFF;for(let i=0;i<b.length;i++)c=CRC[(c^b[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0};
  function zip(files){
    const parts=[],central=[];let off=0;
    const d=new Date(),dt=((d.getHours()<<11)|(d.getMinutes()<<5)|(d.getSeconds()>>1))&0xFFFF,dd=(((d.getFullYear()-1980)<<9)|((d.getMonth()+1)<<5)|d.getDate())&0xFFFF;
    for(const [name,str] of files){
      const nb=enc.encode(name),data=enc.encode(str),crc=crc32(data);
      const h=new DataView(new ArrayBuffer(30));
      h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x0800,true);h.setUint16(8,0,true);h.setUint16(10,dt,true);h.setUint16(12,dd,true);
      h.setUint32(14,crc,true);h.setUint32(18,data.length,true);h.setUint32(22,data.length,true);h.setUint16(26,nb.length,true);h.setUint16(28,0,true);
      parts.push(new Uint8Array(h.buffer),nb,data);
      const c=new DataView(new ArrayBuffer(46));
      c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x0800,true);c.setUint16(10,0,true);c.setUint16(12,dt,true);c.setUint16(14,dd,true);
      c.setUint32(16,crc,true);c.setUint32(20,data.length,true);c.setUint32(24,data.length,true);c.setUint16(28,nb.length,true);c.setUint32(42,off,true);
      central.push(new Uint8Array(c.buffer),nb);
      off+=30+nb.length+data.length;
    }
    const csize=central.reduce((a,b)=>a+b.length,0);
    const e=new DataView(new ArrayBuffer(22));
    e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,csize,true);e.setUint32(16,off,true);
    return new Blob([...parts,...central,new Uint8Array(e.buffer)],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  }
  const x=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F⁦-⁩]/g,'');
  const col=i=>{let s='';i++;while(i){const m=(i-1)%26;s=String.fromCharCode(65+m)+s;i=Math.floor((i-1)/26)}return s};
  function sheetXml(sh){
    const rows=sh.rows,widths=sh.widths||[];
    let out='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0" rightToLeft="1">'+(sh.freeze?'<pane ySplit="'+sh.freeze+'" topLeftCell="A'+(sh.freeze+1)+'" activePane="bottomLeft" state="frozen"/>':'')+'</sheetView></sheetViews>';
    const n=Math.max(0,...rows.map(r=>r.length));
    if(n){out+='<cols>';for(let i=0;i<n;i++)out+='<col min="'+(i+1)+'" max="'+(i+1)+'" width="'+(widths[i]||14)+'" customWidth="1"/>';out+='</cols>'}
    out+='<sheetData>';
    rows.forEach((r,ri)=>{
      const st=(sh.styles&&sh.styles[ri])||0;
      out+='<row r="'+(ri+1)+'">';
      r.forEach((v,ci)=>{
        if(v===null||v===undefined||v==='')return;
        const ref=col(ci)+(ri+1);
        if(typeof v==='number'&&isFinite(v))out+='<c r="'+ref+'" s="'+(st===1?4:st===3?5:2)+'"><v>'+v+'</v></c>';
        else out+='<c r="'+ref+'" t="inlineStr" s="'+(st===1?1:st===3?3:0)+'"><is><t xml:space="preserve">'+x(v)+'</t></is></c>';
      });
      out+='</row>';
    });
    return out+'</sheetData></worksheet>';
  }
  function build(sheets){
    const files=[];
    files.push(['[Content_Types].xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+sheets.map((s,i)=>'<Override PartName="/xl/worksheets/sheet'+(i+1)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join('')+'</Types>']);
    files.push(['_rels/.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>']);
    files.push(['xl/workbook.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>'+sheets.map((s,i)=>'<sheet name="'+x(s.name).slice(0,31)+'" sheetId="'+(i+1)+'" r:id="rId'+(i+1)+'"/>').join('')+'</sheets></workbook>']);
    files.push(['xl/_rels/workbook.xml.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+sheets.map((s,i)=>'<Relationship Id="rId'+(i+1)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+(i+1)+'.xml"/>').join('')+'<Relationship Id="rId'+(sheets.length+1)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>']);
    files.push(['xl/styles.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.##"/></numFmts><fonts count="3"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1D5C86"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE4E7E2"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="6"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"/><xf numFmtId="164" applyNumberFormat="1"/><xf fontId="2" fillId="3" applyFont="1" applyFill="1"/><xf numFmtId="164" fontId="1" fillId="2" applyNumberFormat="1" applyFont="1" applyFill="1"/><xf numFmtId="164" fontId="2" fillId="3" applyNumberFormat="1" applyFont="1" applyFill="1"/></cellXfs></styleSheet>']);
    sheets.forEach((s,i)=>files.push(['xl/worksheets/sheet'+(i+1)+'.xml',sheetXml(s)]));
    return zip(files);
  }
  return {build};
})();

export {XLSX_W};
