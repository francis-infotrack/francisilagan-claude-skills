#!/usr/bin/env node
// ts-complexity: per-function cyclomatic complexity for TS/JS files, via the TypeScript compiler.
//
//   node ts_complexity.cjs <file> ...   ->   JSON {"<file>": [[name, startLine, endLine, ccn], ...]}
//
// lizard's TypeScript reader mis-parses ordinary code (a ternary's `:` read as a type
// annotation swallows the function's closing brace), so crap-gate measures TS/JS here instead.
// `typescript` is resolved from the project (cwd, then each file's directory) — not bundled.
// Exit 3 when it can't be found.
//
// CCN = 1 + if, ?:, for/for-in/for-of, while, do, case (not default), catch, &&, ||, ??
// (and &&= ||= ??=). Optional chaining and default parameters are not decisions here. A nested
// function is its own entry; its decisions do not count toward the enclosing one.
'use strict'
const fs = require('fs')
const path = require('path')

const files = process.argv.slice(2)
let ts
try {
  const paths = [process.cwd(), ...files.map((f) => path.dirname(path.resolve(f)))]
  ts = require(require.resolve('typescript', { paths }))
} catch {
  process.stderr.write('typescript not found from ' + process.cwd() + ' or the measured files (npm install in the project)\n')
  process.exit(3)
}
const K = ts.SyntaxKind

const DECISION_OPERATORS = new Set([
  K.AmpersandAmpersandToken, K.BarBarToken, K.QuestionQuestionToken,
  K.AmpersandAmpersandEqualsToken, K.BarBarEqualsToken, K.QuestionQuestionEqualsToken,
])

function isFunction(node) {
  return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node) ||
    ts.isMethodDeclaration(node) || ts.isConstructorDeclaration(node) ||
    ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)
}

function isDecision(node) {
  switch (node.kind) {
    case K.IfStatement: case K.ConditionalExpression:
    case K.ForStatement: case K.ForInStatement: case K.ForOfStatement:
    case K.WhileStatement: case K.DoStatement:
    case K.CaseClause: case K.CatchClause:
      return true
    case K.BinaryExpression:
      return DECISION_OPERATORS.has(node.operatorToken.kind)
    default:
      return false
  }
}

function nameOf(node) {
  if (ts.isConstructorDeclaration(node)) return 'constructor'
  if (node.name) return node.name.getText()
  const parent = node.parent
  if (parent && (ts.isVariableDeclaration(parent) || ts.isPropertyAssignment(parent) || ts.isPropertyDeclaration(parent)) && parent.name) {
    return parent.name.getText()
  }
  if (parent && ts.isBinaryExpression(parent) && parent.operatorToken.kind === K.EqualsToken) {
    return parent.left.getText()
  }
  return '(anonymous)'
}

function complexityOf(fn) {
  let ccn = 1
  const visit = (node) => {
    if (isFunction(node)) return
    if (isDecision(node)) ccn++
    ts.forEachChild(node, visit)
  }
  ts.forEachChild(fn, visit)
  return ccn
}

function scriptKind(file) {
  const ext = path.extname(file).toLowerCase()
  if (ext === '.tsx') return ts.ScriptKind.TSX
  if (ext === '.jsx') return ts.ScriptKind.JSX
  if (ext === '.js' || ext === '.mjs' || ext === '.cjs') return ts.ScriptKind.JS
  return ts.ScriptKind.TS
}

function measure(file) {
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, scriptKind(file))
  const line = (pos) => source.getLineAndCharacterOfPosition(pos).line + 1
  const out = []
  const visit = (node) => {
    if (isFunction(node) && node.body) {
      out.push([nameOf(node), line(node.getStart(source)), line(node.getEnd()), complexityOf(node)])
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return out
}

const result = {}
for (const file of files) result[file] = measure(file)
process.stdout.write(JSON.stringify(result))
