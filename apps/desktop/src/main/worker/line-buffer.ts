/**
 * Accumulates stream chunks and emits complete newline-delimited lines.
 * Handles CRLF and partial writes from the Python worker.
 */
export class LineBuffer {
  private buffer = ''

  push(chunk: string): string[] {
    this.buffer += chunk
    const parts = this.buffer.split(/\r?\n/)
    this.buffer = parts.pop() ?? ''
    return parts.filter((line) => line.trim().length > 0)
  }

  flush(): string[] {
    const remaining = this.buffer.trim()
    this.buffer = ''
    return remaining.length > 0 ? [remaining] : []
  }
}
