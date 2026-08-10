# Query Examples

This document provides common queries and usage patterns for interacting with the Quantitative Stickynote application's backend.

## Financial Data Queries

### Get Stock Price
```javascript
fetch('/api/stock/price?symbol=AAPL')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Get Historical Data
```javascript
fetch('/api/stock/history?symbol=AAPL&period=1y')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Calculate Returns
```javascript
fetch('/api/calculations/returns', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    startPrice: 150,
    endPrice: 160,
    period: '1y'
  })
})
.then(res => res.json())
.then(data => console.log(data));
```

## Portfolio Queries

### Get Portfolio Summary
```javascript
fetch('/api/portfolio/summary')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Add Position to Portfolio
```javascript
fetch('/api/portfolio/positions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    symbol: 'AAPL',
    quantity: 100,
    entryPrice: 150.00
  })
})
.then(res => res.json())
.then(data => console.log(data));
```

### Remove Position
```javascript
fetch('/api/portfolio/positions/AAPL', {
  method: 'DELETE'
})
.then(res => res.json())
.then(data => console.log(data));
```

## Notes Queries

### Create Note
```javascript
fetch('/api/notes', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: 'Analysis Update',
    content: 'AAPL showing strong momentum...',
    linkedSymbol: 'AAPL',
    color: 'yellow'
  })
})
.then(res => res.json())
.then(data => console.log(data));
```

### Get All Notes
```javascript
fetch('/api/notes')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Search Notes by Symbol
```javascript
fetch('/api/notes?symbol=AAPL')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Update Note
```javascript
fetch('/api/notes/note-id', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    content: 'Updated analysis...',
    color: 'blue'
  })
})
.then(res => res.json())
.then(data => console.log(data));
```

### Delete Note
```javascript
fetch('/api/notes/note-id', {
  method: 'DELETE'
})
.then(res => res.json())
.then(data => console.log(data));
```

## Analysis Queries

### Run Technical Analysis
```javascript
fetch('/api/analysis/technical?symbol=AAPL&indicator=RSI')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Get Sentiment Analysis
```javascript
fetch('/api/analysis/sentiment?symbol=AAPL')
  .then(res => res.json())
  .then(data => console.log(data));
```

### Calculate Metrics
```javascript
fetch('/api/analysis/metrics?symbol=AAPL&metric=PE')
  .then(res => res.json())
  .then(data => console.log(data));
```

## Error Handling

All queries should include error handling:

```javascript
fetch('/api/stock/price?symbol=AAPL')
  .then(res => {
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return res.json();
  })
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));
```

## Response Formats

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error description",
  "code": "ERROR_CODE",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Rate Limiting

- Default: 60 requests per minute per IP
- Authenticated users: 300 requests per minute
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
