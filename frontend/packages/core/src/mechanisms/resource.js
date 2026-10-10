/**
 * 异步资源基类（对齐后端 `BaseAsyncResource`）：统一登记与释放协议。
 *
 * 语义：资源登记后由 `dispose` **逆序释放**、幂等、**释放后拒绝登记**、单个失败不阻断其余。
 */
import { BaseFrameworkObject } from '../base/framework-object';
import { BaseError } from './error';
import { ErrorCodes } from './error-codes';
/** 异步资源基类（抽象）。 */
export class BaseAsyncResource extends BaseFrameworkObject {
    /** 已登记资源（释放时逆序）。 */
    disposables = [];
    /**
     * 登记可释放资源（释放后登记即拒）。
     *
     * @param resource 待登记资源。
     * @throws BaseError 资源已释放（`CAPABILITY_VIOLATION`）。
     */
    registerDisposable(resource) {
        if (this.isDisposed) {
            throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, '资源已释放，拒绝登记');
        }
        this.disposables.push(resource);
    }
    /** 逆序释放已登记资源（单个失败上报后继续）。 */
    onDispose() {
        while (this.disposables.length > 0) {
            const resource = this.disposables.pop();
            try {
                resource.dispose();
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseAsyncResource.dispose' });
            }
        }
    }
}
