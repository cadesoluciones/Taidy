/** Abstract decorative background for the dashboard hero -- a generic
 * data/server network motif (nodes, connecting lines, rack silhouettes),
 * generated inline rather than sourced from a stock photo: nothing here
 * claims to depict real Taidy infrastructure, so a literal photograph would
 * be misleading. Purely decorative -- aria-hidden, no interaction. */
export function DataNetworkArt({ className }: { className?: string | undefined }) {
  return (
    <svg
      className={className}
      viewBox="0 0 480 280"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5">
        <line x1="40" y1="60" x2="140" y2="110" />
        <line x1="140" y1="110" x2="120" y2="210" />
        <line x1="140" y1="110" x2="260" y2="90" />
        <line x1="260" y1="90" x2="360" y2="140" />
        <line x1="260" y1="90" x2="230" y2="200" />
        <line x1="360" y1="140" x2="440" y2="70" />
        <line x1="360" y1="140" x2="420" y2="220" />
        <line x1="120" y1="210" x2="230" y2="200" />
        <line x1="230" y1="200" x2="330" y2="240" />
      </g>
      <g fill="currentColor">
        <circle cx="40" cy="60" r="4" opacity="0.8" />
        <circle cx="140" cy="110" r="6" opacity="0.9" />
        <circle cx="120" cy="210" r="4" opacity="0.7" />
        <circle cx="260" cy="90" r="5" opacity="0.85" />
        <circle cx="360" cy="140" r="6" opacity="0.9" />
        <circle cx="440" cy="70" r="4" opacity="0.7" />
        <circle cx="420" cy="220" r="4" opacity="0.7" />
        <circle cx="230" cy="200" r="5" opacity="0.85" />
        <circle cx="330" cy="240" r="4" opacity="0.7" />
      </g>
      <g stroke="currentColor" strokeWidth="1.5" opacity="0.35">
        <rect x="380" y="20" width="56" height="14" rx="3" />
        <rect x="380" y="38" width="56" height="14" rx="3" />
        <rect x="380" y="56" width="56" height="14" rx="3" />
      </g>
    </svg>
  );
}
