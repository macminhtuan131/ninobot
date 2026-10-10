// Diagnostic only: request physics contact data without changing actuation.
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/plugin/Register.hh>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <stdexcept>
#include <string>

class NinoContactProbe : public gz::sim::System,
                         public gz::sim::ISystemConfigure,
                         public gz::sim::ISystemPreUpdate,
                         public gz::sim::ISystemPostUpdate
{
  std::ofstream stream;
  double last = -1.;
 public:
  void Configure(const gz::sim::Entity &, const std::shared_ptr<const sdf::Element> &sdf,
                 gz::sim::EntityComponentManager &, gz::sim::EventManager &) override
  {
    stream.open(sdf->Get<std::string>("output"));
    if (!stream) throw std::runtime_error("Cannot open contact probe output");
    stream << "sim_time_s,collision,other,points,wrench_points,max_depth_m,force_x_n,force_y_n,force_z_n\n";
    stream << std::setprecision(12);
  }
  void PreUpdate(const gz::sim::UpdateInfo &, gz::sim::EntityComponentManager &ecm) override
  {
    ecm.Each<gz::sim::components::Collision>([&](const auto &entity, const auto *) {
      const auto name = gz::sim::scopedName(entity, ecm, "::", false);
      if (name.find("::nino::") != std::string::npos &&
          !ecm.Component<gz::sim::components::ContactSensorData>(entity))
        ecm.CreateComponent(entity, gz::sim::components::ContactSensorData());
      return true;
    });
  }
  void PostUpdate(const gz::sim::UpdateInfo &info,
                  const gz::sim::EntityComponentManager &ecm) override
  {
    const double t = std::chrono::duration<double>(info.simTime).count();
    if (info.paused || t - last < .02) return;
    last = t;
    ecm.Each<gz::sim::components::Collision, gz::sim::components::ContactSensorData>(
      [&](const auto &entity, const auto *, const auto *data) {
        const auto name = gz::sim::scopedName(entity, ecm, "::", false);
        if (name.find("::nino::") == std::string::npos) return true;
        if (!data->Data().contact_size()) stream << t << ',' << name << ",none,0,0,0,0,0,0\n";
        for (const auto &c : data->Data().contact()) {
          double depth=0, fx=0, fy=0, fz=0;
          for (const auto d : c.depth()) depth = std::max(depth, d);
          for (const auto &w : c.wrench()) {
            fx += w.body_1_wrench().force().x();
            fy += w.body_1_wrench().force().y();
            fz += w.body_1_wrench().force().z();
          }
          stream << t << ',' << name << ',' << c.collision2().name() << ','
                 << c.position_size() << ',' << c.wrench_size() << ',' << depth << ','
                 << fx << ',' << fy << ',' << fz << '\n';
        }
        return true;
      });
    stream.flush();
  }
};
GZ_ADD_PLUGIN(NinoContactProbe, gz::sim::System, gz::sim::ISystemConfigure,
              gz::sim::ISystemPreUpdate, gz::sim::ISystemPostUpdate)
