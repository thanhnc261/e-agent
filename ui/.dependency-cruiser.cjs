/**
 * UI layer boundaries (UI architecture §3): imports only point downward
 * L8 hosts -> L7 layouts -> L6 components -> L5 ui-react -> L3 ui-core -> L2 client;
 * L4 tokens is a leaf used by L6+ hosts. Mirrors import-linter on the Python side.
 */
const pkg = name => `^(packages/${name}/|node_modules/@e-agent/${name}/)`;
const L = {
  client: "client",
  core: "ui-core",
  tokens: "tokens",
  react: "ui-react",
  components: "components",
  layouts: "layouts",
};
const forbid = (name, from, to, comment) => ({
  name,
  comment,
  severity: "error",
  from: { path: `^packages/${from}/src` },
  to: { path: to.map(t => pkg(t)).join("|") },
});

module.exports = {
  forbidden: [
    forbid(
      "client-is-bottom",
      L.client,
      [L.core, L.tokens, L.react, L.components, L.layouts],
      "L2 imports no higher layer",
    ),
    forbid("core-no-ui", L.core, [L.tokens, L.react, L.components, L.layouts], "L3 is framework-free"),
    {
      name: "core-no-frameworks",
      comment: "ui-core and client must not import React or any DOM framework",
      severity: "error",
      from: { path: "^packages/(ui-core|client)/src" },
      to: { path: "node_modules/(react|react-dom|react-aria|react-aria-components|react-stately)/" },
    },
    forbid(
      "tokens-leaf",
      L.tokens,
      [L.client, L.core, L.react, L.components, L.layouts],
      "L4 contains no code deps",
    ),
    forbid(
      "react-below-components",
      L.react,
      [L.components, L.layouts, L.tokens],
      "L5 does not know default components",
    ),
    forbid("components-below-layouts", L.components, [L.layouts, L.client], "L6 reads state only via L5"),
    forbid("layouts-no-client", L.layouts, [L.client], "L7 contains no data access"),
    {
      name: "reference-ui-no-react",
      comment: "the T4 reference UI proves ui-core is enough without React",
      severity: "error",
      from: { path: "^apps/reference-vanilla/src" },
      to: {
        path: "node_modules/(react|react-dom|react-aria|react-aria-components)/|^packages/(ui-react|components|layouts)/",
      },
    },
    {
      name: "no-upward-from-packages-to-apps",
      severity: "error",
      from: { path: "^packages/" },
      to: { path: "^apps/" },
    },
    {
      name: "primitives-are-props-only",
      comment: "L6 primitives are reusable by props alone: no feature, no L5 hook, no transport",
      severity: "error",
      from: { path: "^packages/components/src/primitives/" },
      to: {
        path: "^packages/components/src/features/|^(packages|node_modules/@e-agent)/(ui-react|ui-core|client)/",
      },
    },
    {
      name: "no-cross-feature-imports",
      comment: "features compose through a container or layout, never through each other",
      severity: "error",
      from: { path: "^packages/components/src/features/([^/]+)/" },
      to: {
        path: "^packages/components/src/features/([^/]+)/",
        pathNot: "^packages/components/src/features/$1/",
      },
    },
    {
      name: "no-cross-surface-imports",
      comment: "a placement composes shared/ modules; one surface never imports another",
      severity: "error",
      from: { path: "^packages/layouts/src/(overlay|sidebar|full-page)/" },
      to: {
        path: "^packages/layouts/src/(overlay|sidebar|full-page)/",
        pathNot: "^packages/layouts/src/$1/",
      },
    },
    {
      name: "no-deep-cross-package-imports",
      comment: "reach a sibling package through its declared exports, never into its src",
      severity: "error",
      from: { path: "^(packages|apps)/([^/]+)/" },
      to: {
        path: "^packages/([^/]+)/src/.+",
        pathNot:
          "^packages/$2/|^packages/[^/]+/src/(index\\.tsx?|components\\.css|layouts\\.css|generated/tokens\\.css)$",
      },
    },
    { name: "no-circular", severity: "error", from: {}, to: { circular: true } },
    {
      name: "not-to-unresolvable",
      comment: "an undeclared workspace dependency is a layer violation in disguise",
      severity: "error",
      from: {},
      to: { couldNotResolve: true, pathNot: "\\?inline$" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    exclude: { path: "(^|/)(dist|test-results)/" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "default"],
      extensions: [".ts", ".tsx", ".js", ".mjs"],
    },
  },
};
