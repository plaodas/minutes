try {
  // Provide WebCrypto on globalThis for build tools that expect it.
  if (typeof globalThis.crypto === 'undefined') {
    // Node's built-in webcrypto
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { webcrypto } = require('crypto')
    globalThis.crypto = webcrypto
  }
} catch (e) {
  // ignore
}

module.exports = {}
