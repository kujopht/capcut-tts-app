/**
 * Markdown TỐI GIẢN, AN TOÀN cho nội dung streaming của trợ lý AI — đoạn văn,
 * `**đậm**`, danh sách `- `/`1. `, và `` `code` `` inline. KHÔNG
 * `dangerouslySetInnerHTML`: mọi thứ dựng bằng phần tử React thật, nên không
 * có đường nào để HTML/script do model sinh ra chạy được trong trang.
 *
 * Cố ý tối giản — không bảng, không tiêu đề, không link tự động (link duy
 * nhất hợp lệ là trích dẫn `citations`, dựng riêng ở `AiConversation`).
 */
import { Fragment } from "react";

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // Tách xen kẽ `**đậm**` và `` `code` `` — giữ thứ tự xuất hiện trong chuỗi gốc.
  const re = /\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(<Fragment key={`${keyPrefix}-t${i}`}>{text.slice(last, m.index)}</Fragment>);
    if (m[1] !== undefined) out.push(<strong key={`${keyPrefix}-b${i}`}>{m[1]}</strong>);
    else if (m[2] !== undefined) out.push(<code key={`${keyPrefix}-c${i}`}>{m[2]}</code>);
    last = re.lastIndex;
    i += 1;
  }
  if (last < text.length) out.push(<Fragment key={`${keyPrefix}-t${i}`}>{text.slice(last)}</Fragment>);
  return out;
}

export function renderMarkdownLite(content: string): React.ReactNode {
  const doans = content.split(/\n{2,}/);
  return (
    <>
      {doans.map((doan, di) => {
        const dong = doan.split("\n").filter((d) => d.length > 0);
        const laDanhSach = dong.length > 0 && dong.every((d) => /^\s*([-*]|\d+\.)\s+/.test(d));
        if (laDanhSach) {
          return (
            <ul className="ai-md-ds" key={`p${di}`}>
              {dong.map((d, li) => (
                <li key={li}>{renderInline(d.replace(/^\s*([-*]|\d+\.)\s+/, ""), `p${di}l${li}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p className="ai-md-doan" key={`p${di}`}>
            {doan.split("\n").map((dong2, li) => (
              <Fragment key={li}>
                {li > 0 ? <br /> : null}
                {renderInline(dong2, `p${di}l${li}`)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}
