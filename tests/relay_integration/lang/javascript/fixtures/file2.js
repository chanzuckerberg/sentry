function multiply(a, b) {
  return a * b;
}
function divide(a, b) {
  try {
    return multiply(add(a, b), a, b) / c;
  } catch (e) {
    Raven.captureException(e);
  }
}