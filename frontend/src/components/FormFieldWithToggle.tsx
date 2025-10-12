import { Checkbox } from '@radix-ui/react-checkbox'
import type { FC } from 'react'
import { Input } from './ui/input'

const FormFieldWithToggle: FC<{
    label: string
    name: string
    value: number | null
    checked: boolean
    onToggle: (checked: boolean) => void
}> = ({ label, name, value, checked, onToggle }) => (
    <div className="space-y-1">
        <div className="flex items-center justify-between">
            <label className="text-sm">{label}</label>
            <Checkbox checked={checked} onCheckedChange={onToggle} />
        </div>
        <Input
            type="number"
            name={name}
            defaultValue={value ?? ''}
            step={0.01}
            disabled={!checked}
        />
    </div>
)

export default FormFieldWithToggle
