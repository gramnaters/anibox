import fs from "fs";

const xml = fs.readFileSync("C:\\Users\\visha\\.gemini\\antigravity\\brain\\bb681ad8-2870-40d7-b217-674067e9d9ed\\ui.xml", "utf8");
const textMatches = [...xml.matchAll(/<node[^>]+text="([^"]*Dragon[^"]*)"[^>]*bounds="([^"]+)"/gi)];
for (const m of textMatches) {
  console.log("Text:", m[1], "Bounds:", m[2]);
}

const clickMatches = [...xml.matchAll(/<node[^>]+clickable="true"[^>]*bounds="([^"]+)"[^>]*>/gi)];
console.log("Total clickable:", clickMatches.length);
for (const m of clickMatches.slice(0, 15)) {
  console.log("Clickable:", m[1]);
}
