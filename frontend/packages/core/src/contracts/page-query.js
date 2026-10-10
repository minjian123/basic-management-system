/**
 * 分页查询契约：页码 / 页长 / 排序 / 筛选（与后端分页契约口径一致）。
 */
import { BaseDataObject } from './data-object';
/** 分页查询基类。 */
export class BasePageQuery extends BaseDataObject {
    /** 页码（自 1 起）。 */
    page = 1;
    /** 页长。 */
    size = 20;
    /** 排序字段。 */
    orderBy;
    /** 排序方向。 */
    order;
    /** 偏移量（页码换算）。 */
    get offset() {
        return (this.page - 1) * this.size;
    }
}
