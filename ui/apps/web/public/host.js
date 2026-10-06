// Copy ?lang= / ?theme= onto the element so tests can drive the neutral host page.
(function () {
  var params = new URLSearchParams(location.search);
  var el = document.getElementById("agent");
  if (params.get("lang")) el.setAttribute("lang", params.get("lang"));
  if (params.get("theme")) el.setAttribute("theme", params.get("theme"));
})();
