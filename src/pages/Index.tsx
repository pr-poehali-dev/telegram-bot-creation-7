import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Icon from "@/components/ui/icon";
import { toast } from "sonner";

type UserType = "sender" | "carrier" | null;

interface SenderData {
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

interface Order {
  id: string;
  type: "sender" | "carrier";
  data: SenderData | CarrierData;
  createdAt: Date;
}

const Index = () => {
  const [userType, setUserType] = useState<UserType>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [senderData, setSenderData] = useState<SenderData>({
    pickupAddress: "",
    pickupComments: "",
    warehouse: "",
    deliveryDate: "",
    cargoType: "pallet",
    cargoQuantity: "",
    senderName: "",
    phone: "",
    photo: "",
    labelSize: "120x75",
  });
  const [carrierData, setCarrierData] = useState<CarrierData>({
    carBrand: "",
    carModel: "",
    licensePlate: "",
    capacityType: "pallet",
    capacityQuantity: "",
    warehouse: "",
    driverName: "",
    phone: "",
    licenseNumber: "",
    photo: "",
  });

  const handleSenderSubmit = () => {
    if (!senderData.pickupAddress || !senderData.warehouse || !senderData.senderName || !senderData.phone) {
      toast.error("Заполните обязательные поля");
      return;
    }
    
    const newOrder: Order = {
      id: Date.now().toString(),
      type: "sender",
      data: { ...senderData },
      createdAt: new Date(),
    };
    
    setOrders([newOrder, ...orders]);
    toast.success("Заявка отправителя создана!");
    
    setSenderData({
      pickupAddress: "",
      pickupComments: "",
      warehouse: "",
      deliveryDate: "",
      cargoType: "pallet",
      cargoQuantity: "",
      senderName: "",
      phone: "",
      photo: "",
      labelSize: "120x75",
    });
  };

  const handleCarrierSubmit = () => {
    if (!carrierData.carBrand || !carrierData.licensePlate || !carrierData.driverName || !carrierData.phone) {
      toast.error("Заполните обязательные поля");
      return;
    }
    
    const newOrder: Order = {
      id: Date.now().toString(),
      type: "carrier",
      data: { ...carrierData },
      createdAt: new Date(),
    };
    
    setOrders([newOrder, ...orders]);
    toast.success("Заявка перевозчика создана!");
    
    setCarrierData({
      carBrand: "",
      carModel: "",
      licensePlate: "",
      capacityType: "pallet",
      capacityQuantity: "",
      warehouse: "",
      driverName: "",
      phone: "",
      licenseNumber: "",
      photo: "",
    });
  };

  if (!userType) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md animate-fade-in">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
              <Icon name="Truck" size={32} className="text-primary" />
            </div>
            <CardTitle className="text-2xl">Грузоперевозки</CardTitle>
            <p className="text-muted-foreground mt-2">Выберите тип профиля</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button 
              className="w-full h-14 text-lg" 
              onClick={() => setUserType("sender")}
            >
              <Icon name="PackageOpen" className="mr-2" size={24} />
              Отправитель груза
            </Button>
            <Button 
              className="w-full h-14 text-lg" 
              variant="secondary"
              onClick={() => setUserType("carrier")}
            >
              <Icon name="Truck" className="mr-2" size={24} />
              Перевозчик
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="bg-primary text-primary-foreground p-4 shadow-sm">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button 
              size="icon" 
              variant="ghost" 
              className="text-primary-foreground hover:bg-primary-foreground/10"
              onClick={() => setUserType(null)}
            >
              <Icon name="ArrowLeft" size={24} />
            </Button>
            <div>
              <h1 className="text-lg font-semibold">
                {userType === "sender" ? "Отправитель" : "Перевозчик"}
              </h1>
              <p className="text-sm text-primary-foreground/80">
                {userType === "sender" ? "Создание заявки на доставку" : "Регистрация перевозчика"}
              </p>
            </div>
          </div>
          <Icon name={userType === "sender" ? "PackageOpen" : "Truck"} size={28} />
        </div>
      </div>

      <div className="max-w-4xl mx-auto p-4">
        <Tabs defaultValue="form" className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-6">
            <TabsTrigger value="form">Новая заявка</TabsTrigger>
            <TabsTrigger value="orders">
              Все заявки ({orders.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="form" className="animate-fade-in">
            {userType === "sender" ? (
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

                  <Button className="w-full" size="lg" onClick={handleSenderSubmit}>
                    <Icon name="Send" className="mr-2" size={20} />
                    Создать заявку
                  </Button>
                </CardContent>
              </Card>
            ) : (
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

                  <Button className="w-full" size="lg" onClick={handleCarrierSubmit}>
                    <Icon name="Send" className="mr-2" size={20} />
                    Создать заявку
                  </Button>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="orders" className="animate-fade-in">
            <div className="space-y-4">
              {orders.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <Icon name="Inbox" size={48} className="mx-auto text-muted-foreground mb-4" />
                    <p className="text-muted-foreground">Заявок пока нет</p>
                  </CardContent>
                </Card>
              ) : (
                orders.map((order) => (
                  <Card key={order.id} className="hover-scale">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                            order.type === "sender" ? "bg-blue-100" : "bg-green-100"
                          }`}>
                            <Icon 
                              name={order.type === "sender" ? "PackageOpen" : "Truck"} 
                              size={24}
                              className={order.type === "sender" ? "text-blue-600" : "text-green-600"}
                            />
                          </div>
                          <div>
                            <CardTitle className="text-base">
                              {order.type === "sender" ? "Заявка отправителя" : "Заявка перевозчика"}
                            </CardTitle>
                            <p className="text-sm text-muted-foreground">
                              {new Date(order.createdAt).toLocaleString("ru-RU")}
                            </p>
                          </div>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      {order.type === "sender" ? (
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Отправитель:</span>
                            <span className="font-medium">{(order.data as SenderData).senderName}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Телефон:</span>
                            <span className="font-medium">{(order.data as SenderData).phone}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Адрес забора:</span>
                            <span className="font-medium text-right">{(order.data as SenderData).pickupAddress}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Склад:</span>
                            <span className="font-medium">{(order.data as SenderData).warehouse}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Груз:</span>
                            <span className="font-medium">
                              {(order.data as SenderData).cargoType === "pallet" ? "Паллеты" : "Короба"} 
                              {(order.data as SenderData).cargoQuantity && ` × ${(order.data as SenderData).cargoQuantity}`}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Водитель:</span>
                            <span className="font-medium">{(order.data as CarrierData).driverName}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Телефон:</span>
                            <span className="font-medium">{(order.data as CarrierData).phone}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Автомобиль:</span>
                            <span className="font-medium">
                              {(order.data as CarrierData).carBrand} {(order.data as CarrierData).carModel}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Гос. номер:</span>
                            <span className="font-medium">{(order.data as CarrierData).licensePlate}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Вместимость:</span>
                            <span className="font-medium">
                              {(order.data as CarrierData).capacityType === "pallet" ? "Паллеты" : "Короба"}
                              {(order.data as CarrierData).capacityQuantity && ` × ${(order.data as CarrierData).capacityQuantity}`}
                            </span>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default Index;
