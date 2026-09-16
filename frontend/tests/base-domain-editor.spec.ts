/** 编辑器域基类用例（Kiwi 712）：占位降级 / 去抖上报 / 卸载销毁 / 富文本净化（双端同款）。 */

import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'

import {
  BaseEditor,
  sanitizeHtml,
  useEditorBase,
  type EditorKernelLoader,
  type UseEditorBaseReturn,
} from '@/components/base'

import { mountWithPlugins } from './helpers/mount'

describe('编辑器域基类（Kiwi 712）', () => {
  it('① 占位：无 loader 不加载内核（降级）', async () => {
    const editor = useEditorBase({ modelValue: 'hello' })
    expect(editor.isPlaceholder).toBe(true)
    expect(editor.content).toBe('hello')
    await editor.mount(document.createElement('div'))
    expect(editor.isLoaded).toBe(false)
    expect(editor.getContent()).toBe('hello')
  })

  it('② 即时受控上报与去抖业务上报', () => {
    vi.useFakeTimers()
    try {
      const updates: string[] = []
      const changes: string[] = []
      const editor = useEditorBase({
        debounce: 100,
        onUpdate: (content) => updates.push(content),
        onChange: (content) => changes.push(content),
      })
      editor.onInput('a')
      editor.onInput('ab')
      expect(updates).toEqual(['a', 'ab'])
      expect(changes).toEqual([])
      vi.advanceTimersByTime(100)
      expect(changes).toEqual(['ab'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('③ mount / unmount：内核创建与销毁', async () => {
    const destroyed = vi.fn()
    const loader: EditorKernelLoader = async () => ({
      create: () => ({
        getContent: () => 'kernel-content',
        setContent: () => {},
        destroy: destroyed,
      }),
    })
    const editor = useEditorBase({ loader, modelValue: 'x' })
    expect(editor.isPlaceholder).toBe(false)
    await editor.mount(document.createElement('div'))
    expect(editor.isLoaded).toBe(true)
    expect(editor.getContent()).toBe('kernel-content')
    editor.unmount()
    expect(destroyed).toHaveBeenCalledTimes(1)
  })

  it('④ 只读透传', () => {
    expect(useEditorBase({ readonly: true }).readonly).toBe(true)
    expect(useEditorBase().readonly).toBe(false)
  })

  it('⑤ 内容协议读写与按 kind 净化', () => {
    const rich = useEditorBase({ kind: 'rich' })
    rich.setContent('<p>ok</p><script>alert(1)</script>')
    expect(rich.content).toBe('<p>ok</p>')
    expect(rich.getContent()).toBe('<p>ok</p>')

    const code = useEditorBase({ kind: 'code' })
    code.setContent('<b>x</b>')
    expect(code.content).toBe('<b>x</b>')
    expect(code.sanitize('<i>x</i>')).toBe('<i>x</i>')
  })

  it('⑥ sanitizeHtml 白名单：标签 / 事件属性 / 脚本地址 / 白名单外属性', () => {
    expect(sanitizeHtml('<p onclick="x()">a</p>')).toBe('<p>a</p>')
    expect(sanitizeHtml('<a href="javascript:alert(1)">x</a>')).toBe('<a>x</a>')
    expect(sanitizeHtml('<img src="https://a/b.png" alt="x">')).toBe('<img src="https://a/b.png" alt="x">')
    expect(sanitizeHtml('<iframe src="x"></iframe>')).toBe('')
    expect(sanitizeHtml('<p><span style="color:red">t</span></p>')).toBe('<p><span>t</span></p>')
    expect(sanitizeHtml('<p><strong>保留</strong></p>')).toBe('<p><strong>保留</strong></p>')
  })

  it('⑦ BaseEditor：降级 textarea / 事件 / 工具栏插槽 / 只读', async () => {
    const wrapper = mountWithPlugins(BaseEditor, {
      props: { modelValue: 'hi', placeholder: '写点什么' },
      slots: { toolbar: '<i class="tb">T</i>' },
    })
    expect(wrapper.find('.bms-editor__toolbar').exists()).toBe(true)
    expect(wrapper.find('.tb').exists()).toBe(true)
    const textarea = wrapper.find('textarea')
    expect(textarea.exists()).toBe(true)
    expect((textarea.element as HTMLTextAreaElement).value).toBe('hi')
    expect(textarea.attributes('placeholder')).toBe('写点什么')
    expect(textarea.attributes('readonly')).toBeUndefined()
    await textarea.setValue('hello')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['hello'])
    expect(wrapper.emitted('kernel-ready')).toBeUndefined()

    const readonlyWrapper = mountWithPlugins(BaseEditor, { props: { modelValue: 'x', readonly: true } })
    expect(readonlyWrapper.find('textarea').attributes('readonly')).toBeDefined()

    const hidden = mountWithPlugins(BaseEditor, { props: { visible: false } })
    expect(hidden.find('textarea').exists()).toBe(false)
  })

  it('⑧ BaseEditor：loader 注入触发 kernel-ready 与卸载销毁', async () => {
    const destroyed = vi.fn()
    const loader: EditorKernelLoader = async () => ({
      create: () => ({
        getContent: () => '',
        setContent: () => {},
        destroy: destroyed,
      }),
    })
    const wrapper = mountWithPlugins(BaseEditor, { props: { modelValue: 'x', loader } })
    await flushPromises()
    expect(wrapper.emitted('kernel-ready')).toHaveLength(1)
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
    expect(destroyed).toHaveBeenCalledTimes(1)
  })

  it('⑨ 作用域释放清理未触发的去抖定时器', () => {
    vi.useFakeTimers()
    try {
      const changes: string[] = []
      const scope = effectScope()
      let editor: UseEditorBaseReturn | undefined
      scope.run(() => {
        editor = useEditorBase({ debounce: 50, onChange: (content) => changes.push(content) })
      })
      if (!editor) {
        throw new Error('editor 未创建')
      }
      editor.onInput('a')
      scope.stop()
      vi.advanceTimersByTime(100)
      expect(changes).toEqual([])
    } finally {
      vi.useRealTimers()
    }
  })
})
