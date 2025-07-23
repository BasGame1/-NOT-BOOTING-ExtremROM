import crypto from "crypto";
import { XMLBuilder } from "fast-xml-parser";

import type { FUSMsg } from "../types/FUSMsg";

const builder = new XMLBuilder({});

const getLogicCheck = (input: string, nonce: string) => {
  let out = "";

  for (let i = 0; i < nonce.length; i++) {
    const char: number = nonce.charCodeAt(i);
    out += input[char & 0xf];
  }

  return out;
};

export const getBinaryInformMsg = (
  version: string,
  region: string,
  model: string,
  nonce: string,
  imei: string
): string => {
  let msg: FUSMsg = {
    FUSMsg: {
      FUSHdr: {
        ProtoVer: "1.0",
      },
      FUSBody: {
        Put: {
          ACCESS_MODE: {
            Data: 2,
          },
          BINARY_NATURE: {
            Data: 1,
          },
          CLIENT_PRODUCT: {
            Data: "Smart Switch",
          },
          CLIENT_VERSION: {
            Data: "4.3.23123_1",
          },
          DEVICE_FW_VERSION: {
            Data: version,
          },
          DEVICE_LOCAL_CODE: {
            Data: region,
          },
          DEVICE_MODEL_NAME: {
            Data: model,
          },
          DEVICE_IMEI_PUSH: {
            Data: imei,
          },
          LOGIC_CHECK: {
            Data: getLogicCheck(version, nonce),
          },
        },
      },
    },
  };

  //hardcode EUX as Germany and EUY as Republic of Serbia
  if (region == "EUX") {
    let xelement = msg.FUSMsg.FUSBody.Put;

    xelement.DEVICE_AID_CODE = { Data: region, };
    xelement.DEVICE_CC_CODE = { Data: "DE", };
    xelement.MCC_NUM = { Data: "262", };
    xelement.MNC_NUM = { Data: "01", };

  } else if (region == "EUY") {
    let xelement = msg.FUSMsg.FUSBody.Put;
    
    xelement.DEVICE_AID_CODE = { Data: region, };
    xelement.DEVICE_CC_CODE = { Data: "RS", };
    xelement.MCC_NUM = { Data: "220", };
    xelement.MNC_NUM = { Data: "01", };
  }

  return builder.build(msg);
};

export const getBinaryInitMsg = (filename: string, nonce: string): string => {
  const msg: FUSMsg = {
    FUSMsg: {
      FUSHdr: {
        ProtoVer: "1.0",
      },
      FUSBody: {
        Put: {
          BINARY_FILE_NAME: {
            Data: filename,
          },
          LOGIC_CHECK: {
            Data: getLogicCheck(filename.split(".")[0].slice(-16), nonce),
          },
        },
      },
    },
  };

  return builder.build(msg);
};

export const getDecryptionKey = (
  version: string,
  logicalValue: string
): Buffer => {
  return crypto
    .createHash("md5")
    .update(getLogicCheck(version, logicalValue))
    .digest();
};
