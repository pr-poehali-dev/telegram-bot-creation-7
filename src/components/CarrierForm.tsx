import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import Icon from "@/components/ui/icon";

interface CarrierData {
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

interface CarrierFormProps {
  carrierData: CarrierData;
  setCarrierData: (data: CarrierData) => void;
  onSubmit: () => void;
  loading: boolean;
}

const CarrierForm = ({ carrierData, setCarrierData, onSubmit, loading }: CarrierFormProps) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Данные перевозчика</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="carBrand">Марка авто *</Label>
            <Input
              id="carBrand"
              placeholder="Например: Mercedes"
              value={carrierData.carBrand}
              onChange={(e) => setCarrierData({ ...carrierData, carBrand: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="carModel">Модель</Label>
            <Input
              id="carModel"
              placeholder="Например: Sprinter"
              value={carrierData.carModel}
              onChange={(e) => setCarrierData({ ...carrierData, carModel: e.target.value })}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="licensePlate">Гос. номер *</Label>
          <Input
            id="licensePlate"
            placeholder="А000АА 777"
            value={carrierData.licensePlate}
            onChange={(e) => setCarrierData({ ...carrierData, licensePlate: e.target.value })}
          />
        </div>

        <div>
          <Label>Вместимость</Label>
          <RadioGroup 
            value={carrierData.capacityType}
            onValueChange={(value) => setCarrierData({ ...carrierData, capacityType: value as "pallet" | "box" })}
          >
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="pallet" id="c-pallet" />
              <Label htmlFor="c-pallet">Паллеты</Label>
            </div>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="box" id="c-box" />
              <Label htmlFor="c-box">Короба</Label>
            </div>
          </RadioGroup>
        </div>

        <div>
          <Label htmlFor="capacityQuantity">Количество мест</Label>
          <Input
            id="capacityQuantity"
            type="number"
            placeholder="Максимальная вместимость"
            value={carrierData.capacityQuantity}
            onChange={(e) => setCarrierData({ ...carrierData, capacityQuantity: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="c-warehouse">Склад назначения</Label>
          <Input
            id="c-warehouse"
            placeholder="Куда можете доставить"
            value={carrierData.warehouse}
            onChange={(e) => setCarrierData({ ...carrierData, warehouse: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="driverName">Имя водителя *</Label>
          <Input
            id="driverName"
            placeholder="ФИО водителя"
            value={carrierData.driverName}
            onChange={(e) => setCarrierData({ ...carrierData, driverName: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="c-phone">Контактный телефон *</Label>
          <Input
            id="c-phone"
            type="tel"
            placeholder="+7 (___) ___-__-__"
            value={carrierData.phone}
            onChange={(e) => setCarrierData({ ...carrierData, phone: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="licenseNumber">Номер водительского удостоверения</Label>
          <Input
            id="licenseNumber"
            placeholder="00 00 000000"
            value={carrierData.licenseNumber}
            onChange={(e) => setCarrierData({ ...carrierData, licenseNumber: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="c-photo">Фото авто с номером</Label>
          <Input
            id="c-photo"
            type="file"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                setCarrierData({ ...carrierData, photo: file.name });
              }
            }}
          />
        </div>

        <Button className="w-full" size="lg" onClick={onSubmit} disabled={loading}>
          <Icon name="Send" className="mr-2" size={20} />
          {loading ? "Отправка..." : "Создать заявку"}
        </Button>
      </CardContent>
    </Card>
  );
};

export default CarrierForm;
