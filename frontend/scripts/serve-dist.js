const http = require('http')
const fs = require('fs')
const path = require('path')
const port = process.env.PORT || 5173
const root = path.resolve(__dirname, '..', 'dist')

const mime = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
}

const server = http.createServer((req, res) => {
  let urlPath = req.url.split('?')[0]
  if (urlPath === '/') urlPath = '/index.html'
  const filePath = path.join(root, decodeURIComponent(urlPath))
  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      // fallback to index.html for SPA
      const index = path.join(root, 'index.html')
      fs.readFile(index, (e, data) => {
        if (e) {
          res.writeHead(404)
          res.end('Not found')
        } else {
          res.writeHead(200, { 'Content-Type': 'text/html' })
          res.end(data)
        }
      })
      return
    }
    const ext = path.extname(filePath)
    res.writeHead(200, { 'Content-Type': mime[ext] || 'application/octet-stream' })
    fs.createReadStream(filePath).pipe(res)
  })
})

server.listen(port, () => console.log(`Static server serving ${root} on http://localhost:${port}`))
