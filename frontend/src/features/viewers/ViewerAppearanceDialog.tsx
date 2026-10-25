import { useEffect, useRef, useState } from 'react'

type Props = {
  isOpen: boolean
  theme: string
  density: string
  pending: boolean
  onClose: () => void
  onSave: (theme: string, density: string) => void
}

export function ViewerAppearanceDialog(props: Props) {
  const [theme, setTheme] = useState(props.theme)
  const [density, setDensity] = useState(props.density)
  const first = useRef<HTMLSelectElement>(null)
  useEffect(() => {
    if (props.isOpen) {
      setTheme(props.theme); setDensity(props.density); first.current?.focus()
    }
  }, [props.isOpen, props.theme, props.density])
  if (!props.isOpen) return null
  return <div className="dialog-backdrop" role="presentation">
    <div className="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="appearance-title">
      <span className="eyebrow">APPEARANCE</span><h2 id="appearance-title">表示設定</h2>
      <label htmlFor="appearance-theme">Theme</label><select ref={first} id="appearance-theme" value={theme} onChange={(event) => setTheme(event.target.value)}><option value="technical-light">Technical Light</option><option value="editorial">Editorial</option></select>
      <label htmlFor="appearance-density">Density</label><select id="appearance-density" value={density} onChange={(event) => setDensity(event.target.value)}><option value="comfortable">ゆったり</option><option value="compact">コンパクト</option></select>
      <div className="dialog-actions"><button className="secondary" disabled={props.pending} onClick={props.onClose}>キャンセル</button><button className="primary" disabled={props.pending} onClick={() => props.onSave(theme, density)}>保存</button></div>
    </div>
  </div>
}
