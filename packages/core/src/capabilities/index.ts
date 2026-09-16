/**
 * 能力层出口：导入即完成「已知能力登记 + 能力注册」（不注册不可用）。
 *
 * S1 试点：value / field-shell / field-perm / field（字段链）；S2 扩充其余能力。
 */

import { registerCapability, type CapabilityRegistration } from './registry'
import { BaseValue } from './value'
import { BaseFieldShell } from './field-shell'
import { BaseFieldPerm } from './field-perm'
import { BaseField } from './field'

import './manifest'

const registrations: CapabilityRegistration[] = [
  { key: 'value', depends: [], describe: () => ({ key: 'value' }), create: (options) => new BaseValue(options) },
  {
    key: 'field-shell',
    depends: [],
    describe: () => ({ key: 'field-shell' }),
    create: (options) => new BaseFieldShell(options),
  },
  {
    key: 'field-perm',
    depends: [],
    describe: () => ({ key: 'field-perm' }),
    create: (options) => new BaseFieldPerm(options),
  },
  {
    key: 'field',
    depends: ['value', 'field-shell', 'field-perm'],
    describe: () => ({ key: 'field' }),
    create: (options) => new BaseField(options),
  },
]

for (const registration of registrations) {
  registerCapability(registration)
}

export { BaseValue, type ValueOptions } from './value'
export { BaseFieldShell, type FieldShellOptions } from './field-shell'
export { BaseFieldPerm, type FieldPermOptions } from './field-perm'
export { BaseField, type FieldOptions } from './field'
export {
  CapabilityRegistry,
  capabilityRegistry,
  createCapability,
  registerCapability,
  type CapabilityRegistration,
} from './registry'
export { capabilityManifest } from './manifest'
