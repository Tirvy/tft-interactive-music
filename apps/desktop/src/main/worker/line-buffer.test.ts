import { describe, expect, it } from 'vitest'
import { LineBuffer } from './line-buffer'

describe('LineBuffer', () => {
  it('emits complete lines and retains the partial remainder', () => {
    const buffer = new LineBuffer()

    expect(buffer.push('{"type":"a"}')).toEqual([])
    expect(buffer.push('\n{"type":"b"}\n{"ty')).toEqual(['{"type":"a"}', '{"type":"b"}'])
    expect(buffer.push('pe":"c"}\n')).toEqual(['{"type":"c"}'])
    expect(buffer.flush()).toEqual([])
  })

  it('handles CRLF and blank lines', () => {
    const buffer = new LineBuffer()

    expect(buffer.push('one\r\n\r\ntwo\r\nthree')).toEqual(['one', 'two'])
    expect(buffer.flush()).toEqual(['three'])
  })
})
