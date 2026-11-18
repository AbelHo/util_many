// Dependency-free checks for the keyword engine embedded in audio_annotatorv2.html.
// Usage: node tests/audio_annotator_v2/import_tagging_logic_test.cjs [audacity-labels.txt]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.resolve(__dirname, '../../audio_annotatorv2.html'), 'utf8');
const start = html.indexOf('const IMPORT_STOPWORDS =');
const end = html.indexOf('async function applyImportedAnnotations', start);
assert(start > 0 && end > start, 'Keyword logic anchors should be present in HTML');
const applyEnd = html.indexOf('async function importFile', end);
assert(applyEnd > end);
const app = {markers: new Map(), tags: new Map(), importSources: new Map()};
let nextId = 0;
const engine = vm.runInNewContext(html.slice(start, applyEnd) + `
  ({importLabelTerms, defaultImportCaseSensitive, compileImportFilter,
    importFilterMatches, suggestImportKeywords, importTagPlan, applyImportedAnnotations})`, {
  app, MAX_MARKERS: 1000000, uid: () => `generated-${++nextId}`,
  cleanText: value => value, transactSnapshot: (markers, tags, _, __, sources) =>
    Object.assign(app, {markers, tags, importSources: sources}),
  checkImport: () => {}, yieldUI: async () => {}, status: () => {},
});

function matches(label, term, sensitive, custom = false) {
  const matcher = engine.compileImportFilter(term, sensitive, !custom);
  return engine.importFilterMatches(label, matcher,
    matcher.word !== undefined && !sensitive ? engine.importLabelTerms(label) : null,
    matcher.word !== undefined && sensitive ? engine.importLabelTerms(label, true) : null);
}

async function checkSuggestions(labels, required) {
  const results = await engine.suggestImportKeywords(labels.map(label => ({label})), 0, 0);
  const byTerm = new Map(results.suggestions.map(item => [item.term, item]));
  for (const term of required) {
    assert(byTerm.has(term), `${term} was missing from suggestions: ${[...byTerm.keys()]}`);
    const entry = byTerm.get(term);
    const count = labels.filter(label => matches(label, term, engine.defaultImportCaseSensitive(term))).length;
    assert.equal(entry.count, count, `Default coverage of ${term} should use its actual case`);
  }
  return results;
}

async function main() {
  const labels = [
    'NV | EC | NDA', 'NV | CL | NDA', 'nv | EC? | NDA', 'NM | BP | NDA',
    'NM | bp | NDA', 'Ginger | EC | NDA', 'ec | CL | NDA', 'NV! | BP | NDA',
  ];
  const results = await checkSuggestions(labels, ['NV', 'EC', 'CL', 'BP', 'NDA', 'NM']);
  assert.equal(results.nonempty, 8);
  assert.equal(engine.defaultImportCaseSensitive('NV'), true);
  assert.equal(engine.defaultImportCaseSensitive('EC?'), true);
  assert.equal(engine.defaultImportCaseSensitive('NDA'), true);
  assert.equal(engine.defaultImportCaseSensitive('Ginger'), false);
  assert.equal(labels.filter(label => matches(label, 'NV', true)).length, 3);
  assert.equal(labels.filter(label => matches(label, 'NV', false)).length, 4);
  assert.equal(labels.filter(label => matches(label, 'BP', true)).length, 2);
  assert.equal(labels.filter(label => matches(label, 'bp', true)).length, 1);
  assert.equal(labels.filter(label => matches(label, 'bp', false)).length, 3);
  assert.equal(labels.filter(label => matches(label, 'EC?', true)).length, 1);
  assert.equal(labels.filter(label => matches(label, 'ginger', false)).length, 1);
  assert.equal(matches('Ginger | EC | NDA', 'Ginger EC', false), true);
  assert.equal(matches('NV | CL | NDA', 'NV | CL', true), true);
  assert.equal(matches('a very long word', 'a', true, true), true);
  assert.equal(matches('one | two | three', 'one two three', false, true), true);
  assert.equal(matches('a dolphin appears', 'dolphin', false, true), true);
  assert.equal(matches('clickbait', 'click', false, true), false);
  assert.equal(matches('clickbait', 'click', false), false);
  assert.equal(matches('ECG', 'EC', false), false);
  assert.throws(() => engine.compileImportFilter('', false), /1–128/);

  const plan = engine.importTagPlan({}, {baseTag: null, rules: [
    {term: 'NV', key: 'SightedNV', color: '#123456', caseSensitive: true},
    {term: 'bp', key: 'LowerBP', color: '#abcdef', caseSensitive: true},
  ]});
  assert.equal(plan.rules[0].matcher.caseSensitive, true);
  assert(matches('NV | EC', plan.rules[0].term, plan.rules[0].caseSensitive));
  assert(!matches('nv | EC', plan.rules[0].term, plan.rules[0].caseSensitive));

  await engine.applyImportedAnnotations({
    markers: labels.map((label, i) => ({id: `m${i}`, label, tag: ''})), tags: new Map(),
  }, 'txt', {mode: 'merge', tagPlan: {
    baseTag: {key: 'FileAll', color: '#112233'},
    rules: [
      {term: 'EC?', key: 'QuestionEC', color: '#cc4455', caseSensitive: true, custom: true},
      {term: 'NV', key: 'SightedNV', color: '#123456', caseSensitive: false},
      {term: 'BP', key: 'UpperBP', color: '#abcdef', caseSensitive: true, custom: true},
    ],
  }}, 0, 0, 'coded-labels.txt');
  const tagged = new Map([...app.markers.values()].map(marker => [marker.label, marker.tag]));
  assert.equal(tagged.get('NV | EC | NDA'), 'SightedNV');
  assert.equal(tagged.get('nv | EC? | NDA'), 'QuestionEC'); // Priority overrides NV.
  assert.equal(tagged.get('NM | BP | NDA'), 'UpperBP');
  assert.equal(tagged.get('NM | bp | NDA'), 'FileAll');
  assert.equal(tagged.get('Ginger | EC | NDA'), 'FileAll');
  assert.equal(app.tags.get('QuestionEC').color, '#cc4455');

  // Optional check against the user's imported example without committing it.
  if (process.argv[2]) {
    const actual = fs.readFileSync(process.argv[2], 'utf8').trim().split(/\r?\n/)
      .map(line => line.split('\t').slice(2).join('\t'));
    const observed = await checkSuggestions(actual, ['NV', 'EC', 'CL', 'BP', 'NDA', 'NM']);
    console.log(`Attached-file check: ${actual.length} labels, ${observed.suggestions.length} suggestions`);
  }
  console.log('IMPORT TAGGING LOGIC PASS: codes, spelling, counts, case rules, literals and phrases');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
