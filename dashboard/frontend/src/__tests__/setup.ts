import { TextDecoder, TextEncoder } from "util";

Object.assign(globalThis, {
  TextDecoder,
  TextEncoder,
  IS_REACT_ACT_ENVIRONMENT: true,
});
