/**
 * The e-agent product mark: connected nodes at 15° clockwise, 35° backward tilt,
 * subtle depth, no shadow, glossy surface, Sage Lagoon multicolour. The artwork is
 * the owner-approved logo (regenerated from v4 brand.js with identical parameters);
 * never redraw or recolour it in code.
 * It is decorative — the product name or control label carries the meaning.
 */
import brandMarkSvg from "./brand/e-agent-mark.svg?raw";

export { brandMarkSvg };

export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <span
      className={`ea-brand-mark ${className}`.trim()}
      aria-hidden="true"
      // Trusted, static, build-time asset; no runtime or model-supplied content.
      dangerouslySetInnerHTML={{ __html: brandMarkSvg }}
    />
  );
}
