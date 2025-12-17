import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";

type UserType = "sender" | "carrier";

interface UserTypeSelectorProps {
  onSelectType: (type: UserType) => void;
}

const UserTypeSelector = ({ onSelectType }: UserTypeSelectorProps) => {
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
            onClick={() => onSelectType("sender")}
          >
            <Icon name="PackageOpen" className="mr-2" size={24} />
            Отправитель груза
          </Button>
          <Button 
            className="w-full h-14 text-lg" 
            variant="secondary"
            onClick={() => onSelectType("carrier")}
          >
            <Icon name="Truck" className="mr-2" size={24} />
            Перевозчик
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default UserTypeSelector;
