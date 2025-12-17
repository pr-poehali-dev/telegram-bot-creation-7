export type UserType = "sender" | "carrier" | null;

export interface SenderData {
  pickupAddress: string;
  pickupComments: string;
  warehouse: string;
  deliveryDate: string;
  cargoType: "pallet" | "box";
  cargoQuantity: string;
  senderName: string;
  phone: string;
  photo: string;
  labelSize: "120x75" | "58x40";
}

export interface CarrierData {
  carBrand: string;
  carModel: string;
  licensePlate: string;
  capacityType: "pallet" | "box";
  capacityQuantity: string;
  warehouse: string;
  driverName: string;
  phone: string;
  licenseNumber: string;
  photo: string;
}

export interface Order {
  id: string;
  type: "sender" | "carrier";
  data: SenderData | CarrierData;
  createdAt: Date;
}
