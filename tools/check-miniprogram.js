const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const miniprogram = path.join(root, 'miniprogram');

function requireFile(filePath, label) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Missing ${label}: ${path.relative(root, filePath)}`);
  }
}

function parseJson(filePath) {
  requireFile(filePath, 'JSON file');
  JSON.parse(fs.readFileSync(filePath, 'utf8'));
  console.log(`JSON OK ${path.relative(root, filePath)}`);
}

function walk(directory, extension) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return walk(target, extension);
    return target.endsWith(extension) ? [target] : [];
  });
}

function walkTextFiles(directory) {
  const textExtensions = new Set(['.js', '.json', '.wxml', '.wxss']);
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return walkTextFiles(target);
    return textExtensions.has(path.extname(target)) ? [target] : [];
  });
}

walkTextFiles(miniprogram).forEach((filePath) => {
  const bytes = fs.readFileSync(filePath);
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    throw new Error(`UTF-8 BOM is not allowed: ${path.relative(root, filePath)}`);
  }
});
console.log('Text encoding OK no UTF-8 BOM');

parseJson(path.join(miniprogram, 'app.json'));
parseJson(path.join(miniprogram, 'project.config.json'));
parseJson(path.join(miniprogram, 'sitemap.json'));

const appJson = JSON.parse(fs.readFileSync(path.join(miniprogram, 'app.json'), 'utf8'));
appJson.pages.forEach((route) => {
  ['.js', '.json', '.wxml', '.wxss'].forEach((extension) => {
    requireFile(path.join(miniprogram, `${route}${extension}`), `route file ${route}${extension}`);
  });
  console.log(`Route OK ${route}`);
});

appJson.tabBar.list.forEach((item) => {
  requireFile(path.join(miniprogram, item.iconPath), `tabbar icon ${item.iconPath}`);
  requireFile(path.join(miniprogram, item.selectedIconPath), `tabbar icon ${item.selectedIconPath}`);
});
console.log(`TabBar assets OK ${appJson.tabBar.list.length}`);

walk(miniprogram, '.js').forEach((filePath) => {
  new vm.Script(fs.readFileSync(filePath, 'utf8'), { filename: filePath });
  console.log(`JS OK ${path.relative(root, filePath)}`);
});

const decorRoot = path.join(root, 'demo_data', 'decor_info');
const decorClasses = fs.readdirSync(decorRoot, { withFileTypes: true }).filter((entry) => entry.isDirectory());
decorClasses.forEach((entry) => {
  requireFile(path.join(decorRoot, entry.name, 'bigImage.jpg'), `decor image ${entry.name}`);
  requireFile(path.join(decorRoot, entry.name, 'metadata.json'), `decor metadata ${entry.name}`);
});
console.log(`Scanned decor assets OK ${decorClasses.length}`);
console.log('Mini program release check passed.');
