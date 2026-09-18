/**
 * 注册项公共契约（对齐后端 `BaseProvider`）。
 *
 * 继承能力域基类而**不继承**插件基类——走**组合轨**（经域注册表 / 显式登记接入），
 * 不进入继承自动登记。抽象 `key` 与自描述 `describe` 由各域注册项实现。
 */

import { BaseCapability } from './capability'

/** 注册项基类（抽象）。 */
export abstract class BaseProvider extends BaseCapability {}
