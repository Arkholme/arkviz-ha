
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="c9d798d8-f5ba-520f-a8d0-1d2a093aeefa")}catch(e){}}();
var e={downlight:1626,pendant:1473,lamp:1270,sconce:1168};function t(t,n=100){return(e[t]??1270)*(.6+n/100*.4)}function n(e=100){return .45+e/100*.55}function r(e){if(!e.startsWith(`#`))return e.replace(/[\d.]+%?\)\s*$/,`0)`);let t=e.slice(1);return t.length<=4?`#${t.slice(0,3)}0`:`#${t.slice(0,6)}00`}export{n,t as r,r as t};
//# debugId=c9d798d8-f5ba-520f-a8d0-1d2a093aeefa
