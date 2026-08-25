/**
 * OriginPage — "À propos": what this project is, the real-world problem
 * it addresses (curtailment / negative electricity prices), and how it works.
 */
export default function OriginPage() {
  return (
    <main id="main-content" className="app-main content-page">
      <section className="glass-card content-card">
        <p className="content-kicker">À propos</p>
        <p>
          Ce projet répond à une problématique rencontrée lors de mon alternance au sein
          d'un exploitant de parcs éoliens et solaires. Lorsque la production de
          renouvelable dépasse la demande — par exemple lors de vents forts pour
          l'éolien et au zénith pour le solaire — le prix de l'électricité peut devenir
          négatif : les producteurs paient pour injecter leur courant dans le réseau. Il
          est alors préférable de mettre une partie des turbines à l'arrêt. Cette
          manœuvre, intitulée curtailment, est donc moins coûteuse plus sa décision est
          prise tôt.
        </p>
        <p>
          Ainsi, ce dashboard permet de l'anticiper régionalement en surveillant la
          production et la consommation de l'énergie toutes sources confondues. Pour ce
          faire, il recueille toutes les 15 minutes les données publiées par RTE et les
          croise avec la météo et les alertes de maintenance, qui sont stockées dans un
          data lake pour être nettoyées avant d'être mises en base de données.
        </p>
      </section>
    </main>
  )
}
