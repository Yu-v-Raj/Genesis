/**
 * The saved sidebar preference, shared by the root layout (server) and the sidebar hook (client).
 *
 * The visual collapsed state is driven by `data-sidebar="collapsed"` on <html>, not by React
 * state. A blocking inline script in <head> sets that attribute from localStorage while the
 * HTML is parsed, so the first paint already has the saved width; React hydrates afterwards
 * without changing anything visible. (Next.js guide: "Preventing flash before hydration".)
 */

export const SIDEBAR_STORAGE_KEY = "genesis.sidebar.collapsed";
export const SIDEBAR_ATTRIBUTE = "data-sidebar";
export const SIDEBAR_COLLAPSED = "collapsed";

/** Runs before first paint. Storage may be unavailable, so failures leave the default. */
export const SIDEBAR_INIT_SCRIPT = `(function(){try{if(localStorage.getItem(${JSON.stringify(SIDEBAR_STORAGE_KEY)})==="true")document.documentElement.setAttribute(${JSON.stringify(SIDEBAR_ATTRIBUTE)},${JSON.stringify(SIDEBAR_COLLAPSED)})}catch(e){}})()`;
