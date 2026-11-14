import { execSync } from "child_process";
import fs from "fs";

const ADB = process.env.LOCALAPPDATA + "\\Android\\Sdk\\platform-tools\\adb.exe";

export function getUiXml() {
  execSync(`"${ADB}" shell uiautomator dump /sdcard/ui.xml`, { stdio: "ignore" });
  const xml = execSync(`"${ADB}" shell cat /sdcard/ui.xml`).toString("utf-8");
  return xml;
}

export function findNodeByText(text, xml = null) {
  if (!xml) xml = getUiXml();
  const regex = new RegExp(`<node[^>]*text="([^"]*${text}[^"]*)"[^>]*bounds="(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`, "i");
  // Also match standard bounds="[x1,y1][x2,y2]"
  const match = xml.match(new RegExp(`<node[^>]*text="([^"]*${text}[^"]*)"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`, "i")) ||
                xml.match(new RegExp(`<node[^>]*content-desc="([^"]*${text}[^"]*)"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`, "i"));

  if (!match) return null;
  const matchedText = match[1];
  const x1 = parseInt(match[2], 10);
  const y1 = parseInt(match[3], 10);
  const x2 = parseInt(match[4], 10);
  const y2 = parseInt(match[5], 10);
  const centerX = Math.floor((x1 + x2) / 2);
  const centerY = Math.floor((y1 + y2) / 2);

  return { text: matchedText, x1, y1, x2, y2, centerX, centerY };
}

export function tapByText(text) {
  const node = findNodeByText(text);
  if (!node) {
    console.error(`Element with text "${text}" not found in current UI hierarchy.`);
    return false;
  }
  console.log(`Tapping "${node.text}" at dynamic center (${node.centerX}, ${node.centerY})...`);
  execSync(`"${ADB}" shell input tap ${node.centerX} ${node.centerY}`);
  return true;
}

export function takeScreenshot(outputPath) {
  execSync(`"${ADB}" shell screencap -p /sdcard/screen.png`);
  execSync(`"${ADB}" pull /sdcard/screen.png "${outputPath}"`);
}
