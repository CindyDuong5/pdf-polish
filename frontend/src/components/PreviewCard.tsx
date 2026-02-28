// frontend/src/components/PreviewCard.tsx
export default function PreviewCard({
  title,
  url,
  reloadKey,
}: {
  title: string;
  url: string | null;
  reloadKey: number;
}) {
  return (
    <div>
      <div className="previewHeader">
        <div className="previewTitle">{title}</div>
        {url ? (
          <a className="link" href={url} target="_blank" rel="noreferrer">
            Open in new tab
          </a>
        ) : (
          <span className="mutedSmall">Not available</span>
        )}
      </div>

      <div className="previewFrame">
        {url ? (
          <iframe
            key={`${title}-${reloadKey}`}
            title={title}
            src={url}
            style={{ width: "100%", height: "100%", border: "0" }}
          />
        ) : (
          <div className="mutedSmall" style={{ padding: 12 }}>
            No PDF yet. It will appear automatically once processing is done.
          </div>
        )}
      </div>
    </div>
  );
}