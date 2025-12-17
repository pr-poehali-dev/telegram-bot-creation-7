import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import Icon from "@/components/ui/icon";
import type { SenderData } from "@/types";

interface SenderFormProps {
  senderData: SenderData;
  setSenderData: (data: SenderData) => void;
  onSubmit: () => void;
  loading: boolean;
}

const SenderForm = ({ senderData, setSenderData, onSubmit, loading }: SenderFormProps) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Данные о грузе</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label htmlFor="pickupAddress">Адрес забора груза *</Label>
          <Input
            id="pickupAddress"
            placeholder="Введите адрес"
            value={senderData.pickupAddress}
            onChange={(e) => setSenderData({ ...senderData, pickupAddress: e.target.value })}
          />
        </div>
        
        <div>
          <Label htmlFor="pickupComments">Комментарии (как проехать)</Label>
          <Textarea
            id="pickupComments"
            placeholder="Укажите дополнительные детали"
            value={senderData.pickupComments}
            onChange={(e) => setSenderData({ ...senderData, pickupComments: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="warehouse">Склад назначения *</Label>
          <Input
            id="warehouse"
            placeholder="Название или адрес склада"
            value={senderData.warehouse}
            onChange={(e) => setSenderData({ ...senderData, warehouse: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="deliveryDate">Дата поставки</Label>
          <Input
            id="deliveryDate"
            type="date"
            value={senderData.deliveryDate}
            onChange={(e) => setSenderData({ ...senderData, deliveryDate: e.target.value })}
          />
        </div>

        <div>
          <Label>Вид груза</Label>
          <RadioGroup 
            value={senderData.cargoType}
            onValueChange={(value) => setSenderData({ ...senderData, cargoType: value as "pallet" | "box" })}
          >
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="pallet" id="pallet" />
              <Label htmlFor="pallet">Паллеты</Label>
            </div>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="box" id="box" />
              <Label htmlFor="box">Короба</Label>
            </div>
          </RadioGroup>
        </div>

        <div>
          <Label htmlFor="cargoQuantity">Количество</Label>
          <Input
            id="cargoQuantity"
            type="number"
            placeholder="Введите количество"
            value={senderData.cargoQuantity}
            onChange={(e) => setSenderData({ ...senderData, cargoQuantity: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="senderName">Имя отправителя *</Label>
          <Input
            id="senderName"
            placeholder="ФИО"
            value={senderData.senderName}
            onChange={(e) => setSenderData({ ...senderData, senderName: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="phone">Контактный телефон *</Label>
          <Input
            id="phone"
            type="tel"
            placeholder="+7 (___) ___-__-__"
            value={senderData.phone}
            onChange={(e) => setSenderData({ ...senderData, phone: e.target.value })}
          />
        </div>

        <div>
          <Label htmlFor="photo">Фото груза</Label>
          <Input
            id="photo"
            type="file"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                setSenderData({ ...senderData, photo: file.name });
              }
            }}
          />
        </div>

        <div>
          <Label>Размер термонаклейки</Label>
          <RadioGroup 
            value={senderData.labelSize}
            onValueChange={(value) => setSenderData({ ...senderData, labelSize: value as "120x75" | "58x40" })}
          >
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="120x75" id="size1" />
              <Label htmlFor="size1">120 × 75 мм</Label>
            </div>
            <div className="flex items-center space-x-2">
              <RadioGroupItem value="58x40" id="size2" />
              <Label htmlFor="size2">58 × 40 мм</Label>
            </div>
          </RadioGroup>
        </div>

        <Button className="w-full" size="lg" onClick={onSubmit} disabled={loading}>
          <Icon name="Send" className="mr-2" size={20} />
          {loading ? "Отправка..." : "Создать заявку"}
        </Button>
      </CardContent>
    </Card>
  );
};

export default SenderForm;