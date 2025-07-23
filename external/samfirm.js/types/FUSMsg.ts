export interface FUSMsg {
  FUSMsg: {
    FUSHdr: {
      ProtoVer: string;
    };
    FUSBody: {
      Put: {
        DEVICE_AID_CODE?: {
          Data: string;
        };
        DEVICE_CC_CODE?: {
          Data: string;
        };
        MCC_NUM?: {
          Data: string;
        };
        MNC_NUM?: {
          Data: string;
        };
        ACCESS_MODE?: {
          Data: number;
        };
        BINARY_FILE_NAME?: {
          Data: string;
        };
        BINARY_NATURE?: {
          Data: number;
        };
        CLIENT_PRODUCT?: {
          Data: string;
        };
        CLIENT_VERSION?: {
          Data: string;
        };
        DEVICE_FW_VERSION?: {
          Data: string;
        };
        DEVICE_LOCAL_CODE?: {
          Data: string;
        };
        DEVICE_MODEL_NAME?: {
          Data: string;
        };
        DEVICE_IMEI_PUSH?: {
          Data: string;
        };
        LOGIC_CHECK?: {
          Data: string;
        };
      };
    };
  };
}
