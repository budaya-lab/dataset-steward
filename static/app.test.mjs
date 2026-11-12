import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { createContext, runInContext } from 'node:vm';

function app() {
  const context = createContext({
    document: { querySelector: () => ({ addEventListener() {} }) },
    window: { addEventListener() {} },
    fetch: () => new Promise(() => {}),
  });
  runInContext(readFileSync(new URL('./app.js', import.meta.url), 'utf8'), context);
  return context;
}

test('formats computed counts with resource units', () => {
  const { countText } = app();
  assert.equal(countText({ path: 'input.csv', count: 2 }), '2 rows');
  assert.equal(countText({ path: 'input.csv', count: 0 }), '0 rows');
  assert.equal(countText({ path: 'items.json', count: 1 }), '1 item');
  assert.equal(countText({ path: 'annotations/', count: 2 }), '2 files');
});

test('does not display legacy sizes or invalid counts', () => {
  const { countText } = app();
  assert.equal(countText({ path: 'input.csv', size: 10 }), '');
  for (const count of [undefined, null, true, -1, 1.5, '2', 9007199254740992]) {
    assert.equal(countText({ path: 'input.csv', count }), '');
  }
});

test('resource editor labels and displays counts', () => {
  const context = app();
  const sections = [];
  context.el = (tag, props, ...children) => ({ tag, props, children });
  context.rowSection = (section) => { sections.push(section); return section; };
  runInContext('state.pkg = {}; state.detail = { stages: [], stubs: [] }; renderEdit();', context);
  const resources = sections.find((section) => section.key === 'resources');
  assert.equal(resources.headers.at(-1), 'Count');
  assert.match(resources.hint, /counted automatically/i);
  assert.equal(resources.cells({ path: 'annotations/', count: 2 }).at(-1).children[0], '2 files');
});
