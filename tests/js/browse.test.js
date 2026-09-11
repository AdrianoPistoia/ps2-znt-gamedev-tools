const assert = require("assert");
const A = require(require("path").join(__dirname, "../../znt/web/static/logic.js"));

assert.deepStrictEqual(A.crumbs("/home/adri/Downloads"), [
  { name: "/",         path: "/" },
  { name: "home",      path: "/home" },
  { name: "adri",      path: "/home/adri" },
  { name: "Downloads", path: "/home/adri/Downloads" },
]);
assert.deepStrictEqual(A.crumbs("/"), [{ name: "/", path: "/" }]);
assert.deepStrictEqual(A.crumbs(""), []);
assert.strictEqual(A.crumbs("/a/b/").length, 3, "a trailing slash does not add a segment");

// join folder + name for 'save as'
assert.strictEqual(A.joinPath("/home/adri", "h.vn"), "/home/adri/h.vn");
assert.strictEqual(A.joinPath("/", "h.vn"), "/h.vn");
assert.strictEqual(A.joinPath("/home/adri/", "h.vn"), "/home/adri/h.vn");
console.log("BROWSE JS GREEN");
