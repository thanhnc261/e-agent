// v5 identity: the v4 connected-node geometry rendered at the owner's 2026-10-11 pose.
// Geometry stays single-source in ../agentic-chat-v4/design-system/brand.js; only parameters change here.
import { logoGlyphFor, wordmark } from "../agentic-chat-v4/design-system/brand.js";

export const pose = Object.freeze({
  rotation: 15,
  tilt: 35,
  depth: 1,
  shadow: "none",
  finish: "glossy",
});
export const poseCaption = "15° clockwise · 35° backward tilt · subtle depth · no shadow · glossy surface";
export const v4Pose = Object.freeze({ rotation: 22.5, tilt: 35, depth: 3, shadow: "soft", finish: "glossy" });

const glyph = logoGlyphFor(pose);
const svg = (inner, label = "") =>
  `<svg class="ea-brand-symbol" viewBox="0 0 32 32" ${label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"'} focusable="false">${inner}</svg>`;

export const logo = () => svg(glyph);
export const logoFor = (p, label) => svg(logoGlyphFor(p), label);
export const standaloneSvg = (color, p = pose) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="256" height="256" style="color:${color}">${logoGlyphFor(p)}</svg>`;
export { wordmark };
